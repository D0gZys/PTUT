#include "csv_recorder.h"

#include <QDateTime>
#include <QDir>
#include <QTextStream>
#include <QtGlobal>

namespace {
constexpr int kTriggerPreLines = 200;
constexpr int kTriggerPostLines = 200;
constexpr int kDefaultSampleCount = 475;
constexpr int kStatusInterval = 50;
constexpr int kFlushInterval = 100;
}

CsvRecorder::CsvRecorder(QObject *parent)
    : QObject(parent),
      m_recording(false),
      m_triggerEnabled(false),
      m_aboveThreshold(false),
      m_triggerThreshold(-130.0),
      m_triggerMaxDbm(-999.0),
      m_triggerCount(0),
      m_postRemaining(0),
      m_linesWritten(0),
      m_freqMHz(0.0),
      m_spanKHz(5.0),
      m_refLevel(0),
      m_sampleCount(kDefaultSampleCount),
      m_headerWritten(false) {
}

bool CsvRecorder::recording() const {
    return m_recording;
}

bool CsvRecorder::triggerEnabled() const {
    return m_triggerEnabled;
}

double CsvRecorder::triggerThreshold() const {
    return m_triggerThreshold;
}

QString CsvRecorder::statusText() const {
    return m_statusText;
}

void CsvRecorder::start() {
    if (m_recording) {
        return;
    }

    if (m_triggerEnabled) {
        m_aboveThreshold = false;
        m_triggerCount = 0;
        m_postRemaining = 0;
        m_triggerMaxDbm = -999.0;
        m_preBuffer.clear();
        updateStatus(QString("TRIGGER: attente > %1 dBm").arg(m_triggerThreshold, 0, 'f', 0));
    } else {
        if (!openCsv(false)) {
            return;
        }
        updateStatus("REC: 0 lignes");
    }

    m_recording = true;
    emit recordingChanged();
}

void CsvRecorder::stop() {
    if (!m_recording) {
        return;
    }
    m_recording = false;
    emit recordingChanged();

    closeCsv(true);
    m_preBuffer.clear();
    updateStatus("");
}

void CsvRecorder::toggle() {
    if (m_recording) {
        stop();
    } else {
        start();
    }
}

void CsvRecorder::setTriggerEnabled(bool enabled) {
    if (m_triggerEnabled == enabled) {
        return;
    }
    m_triggerEnabled = enabled;
    emit triggerEnabledChanged();
}

void CsvRecorder::setTriggerThreshold(double value) {
    if (qFuzzyCompare(m_triggerThreshold, value)) {
        return;
    }
    m_triggerThreshold = value;
    emit triggerThresholdChanged();
}

void CsvRecorder::setCurrentFreqMHz(double value) {
    if (qFuzzyCompare(m_freqMHz, value)) {
        return;
    }
    m_freqMHz = value;
}

void CsvRecorder::setCurrentSpanKHz(double value) {
    if (qFuzzyCompare(m_spanKHz, value)) {
        return;
    }
    m_spanKHz = value;
}

void CsvRecorder::setRefLevel(int value) {
    if (m_refLevel == value) {
        return;
    }
    m_refLevel = value;
}

void CsvRecorder::pushSamples(const QVector<float> &samples) {
    if (!m_recording || samples.isEmpty()) {
        return;
    }

    if (m_sampleCount != samples.size()) {
        m_sampleCount = samples.size();
    }

    Frame frame;
    frame.timestamp = nowTimestamp();
    frame.freqMHz = m_freqMHz;
    frame.spanKHz = m_spanKHz;
    frame.refLevel = m_refLevel;
    frame.samples = samples;

    float maxSignal = samples[0];
    for (float value : samples) {
        if (value > maxSignal) {
            maxSignal = value;
        }
    }

    if (m_triggerEnabled) {
        if (maxSignal >= m_triggerThreshold) {
            if (!m_aboveThreshold) {
                m_aboveThreshold = true;
                if (!m_file.isOpen()) {
                    m_triggerCount += 1;
                    if (!openCsv(true)) {
                        m_recording = false;
                        emit recordingChanged();
                        return;
                    }
                    for (const Frame &buffered : m_preBuffer) {
                        writeFrame(buffered);
                        float bufMax = buffered.samples.isEmpty() ? -999.0f : buffered.samples[0];
                        for (float value : buffered.samples) {
                            if (value > bufMax) {
                                bufMax = value;
                            }
                        }
                        if (bufMax > m_triggerMaxDbm) {
                            m_triggerMaxDbm = bufMax;
                        }
                    }
                    m_preBuffer.clear();
                }
            }

            m_postRemaining = kTriggerPostLines;
            if (maxSignal > m_triggerMaxDbm) {
                m_triggerMaxDbm = maxSignal;
            }
            if (m_file.isOpen()) {
                writeFrame(frame);
                updateStatus(QString("TRIGGER #%1: %2 lignes | Max: %3 dBm")
                                 .arg(m_triggerCount)
                                 .arg(m_linesWritten)
                                 .arg(m_triggerMaxDbm, 0, 'f', 1));
            }
        } else {
            if (m_aboveThreshold) {
                m_aboveThreshold = false;
            }

            if (m_file.isOpen()) {
                if (m_postRemaining > 0) {
                    writeFrame(frame);
                    m_postRemaining -= 1;
                    if (m_postRemaining <= 0) {
                        closeCsv(true);
                        updateStatus(QString("TRIGGER: attente > %1 dBm").arg(m_triggerThreshold, 0, 'f', 0));
                    }
                } else {
                    closeCsv(true);
                    updateStatus(QString("TRIGGER: attente > %1 dBm").arg(m_triggerThreshold, 0, 'f', 0));
                }
            }

            if (!m_file.isOpen()) {
                enqueuePreBuffer(frame);
            }
        }
        return;
    }

    if (m_file.isOpen()) {
        writeFrame(frame);
        if (m_linesWritten % kStatusInterval == 0) {
            updateStatus(QString("REC: %1 lignes").arg(m_linesWritten));
        }
    }
}

bool CsvRecorder::openCsv(bool triggerTemp) {
    if (m_file.isOpen()) {
        m_file.close();
    }

    const QString folder = makeDayFolder();
    if (folder.isEmpty()) {
        updateStatus("CSV: dossier introuvable");
        return false;
    }

    const QString ts = QDateTime::currentDateTime().toString("HHmmss");
    QString fileName;
    if (triggerTemp) {
        m_triggerMaxDbm = -999.0;
        fileName = QString("trigger_%1dBm_%2_TEMP.csv")
                       .arg(int(m_triggerThreshold))
                       .arg(ts);
    } else {
        fileName = QString("spectre_%1.csv").arg(ts);
    }

    m_filePath = QDir(folder).filePath(fileName);
    m_file.setFileName(m_filePath);
    if (!m_file.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        updateStatus(QString("CSV: erreur %1").arg(m_file.errorString()));
        return false;
    }

    m_linesWritten = 0;
    m_headerWritten = false;
    writeHeader(m_sampleCount);
    return true;
}

void CsvRecorder::closeCsv(bool finalizeTrigger) {
    if (m_file.isOpen()) {
        m_file.close();
    }

    if (finalizeTrigger && m_triggerEnabled && m_filePath.endsWith("_TEMP.csv")) {
        if (QFile::exists(m_filePath)) {
            const int maxValue = int(m_triggerMaxDbm);
            const QString newPath = m_filePath;
            const QString newName = newPath.left(newPath.size() - QString("_TEMP.csv").size()) +
                                    QString("_max%1dBm.csv").arg(maxValue);
            QFile::rename(m_filePath, newName);
            m_filePath = newName;
        }
    }

    m_filePath.clear();
    m_linesWritten = 0;
    m_headerWritten = false;
}

void CsvRecorder::writeHeader(int sampleCount) {
    if (!m_file.isOpen()) {
        return;
    }
    const int count = sampleCount > 0 ? sampleCount : kDefaultSampleCount;
    QTextStream stream(&m_file);
    stream << "timestamp,freq_mhz,span_khz,ref_level_dbm";
    for (int i = 0; i < count; ++i) {
        stream << ",dbm_" << i;
    }
    stream << "\n";
    m_headerWritten = true;
}

void CsvRecorder::writeFrame(const Frame &frame) {
    if (!m_file.isOpen()) {
        return;
    }
    if (!m_headerWritten) {
        writeHeader(frame.samples.size());
    }
    QTextStream stream(&m_file);
    stream << frame.timestamp << ","
           << QString::number(frame.freqMHz, 'f', 6) << ","
           << QString::number(frame.spanKHz, 'f', 3) << ","
           << frame.refLevel;
    for (float value : frame.samples) {
        stream << "," << QString::number(value, 'f', 1);
    }
    stream << "\n";

    m_linesWritten += 1;
    if (m_linesWritten % kFlushInterval == 0) {
        m_file.flush();
    }
}

QString CsvRecorder::makeDayFolder() const {
    const QString dateFolder = QDateTime::currentDateTime().toString("yyyyMMdd");
    QDir base(QDir::currentPath());
    QString recepPath;
    for (int i = 0; i < 4; ++i) {
        if (base.exists("recep_csv")) {
            recepPath = base.filePath("recep_csv");
            break;
        }
        if (!base.cdUp()) {
            break;
        }
    }
    if (recepPath.isEmpty()) {
        recepPath = QDir::current().filePath("recep_csv");
    }

    QDir recepDir(recepPath);
    if (!recepDir.exists()) {
        if (!QDir().mkpath(recepPath)) {
            return QString();
        }
    }

    if (!recepDir.exists(dateFolder)) {
        if (!recepDir.mkpath(dateFolder)) {
            return QString();
        }
    }

    return recepDir.filePath(dateFolder);
}

QString CsvRecorder::nowTimestamp() const {
    return QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz");
}

void CsvRecorder::updateStatus(const QString &text) {
    if (m_statusText == text) {
        return;
    }
    m_statusText = text;
    emit statusTextChanged();
}

void CsvRecorder::enqueuePreBuffer(const Frame &frame) {
    while (m_preBuffer.size() >= kTriggerPreLines) {
        m_preBuffer.dequeue();
    }
    m_preBuffer.enqueue(frame);
}
