#include "csv_replay.h"

#include <QFile>
#include <QtGlobal>
#include <QTextStream>
#include <QUrl>

namespace {
constexpr int kSpectrumWidth = 475;
constexpr int kWaterfallDepth = 200;
}

CsvReplay::CsvReplay(QObject *parent)
    : QObject(parent),
      m_loaded(false),
      m_currentIndex(-1),
      m_playing(false),
      m_speed(1.0),
      m_currentFreqMHz(0.0),
      m_currentSpanKHz(0.0),
      m_waterfallDepth(kWaterfallDepth) {
    m_timer.setTimerType(Qt::CoarseTimer);
    connect(&m_timer, &QTimer::timeout, this, &CsvReplay::next);
    updateTimer();
}

bool CsvReplay::loaded() const {
    return m_loaded;
}

int CsvReplay::lineCount() const {
    return m_frames.size();
}

int CsvReplay::currentIndex() const {
    return m_currentIndex;
}

QString CsvReplay::currentTimestamp() const {
    return m_currentTimestamp;
}

QString CsvReplay::lastError() const {
    return m_lastError;
}

bool CsvReplay::playing() const {
    return m_playing;
}

double CsvReplay::speed() const {
    return m_speed;
}

double CsvReplay::currentFreqMHz() const {
    return m_currentFreqMHz;
}

double CsvReplay::currentSpanKHz() const {
    return m_currentSpanKHz;
}

int CsvReplay::waterfallDepth() const {
    return m_waterfallDepth;
}

bool CsvReplay::loadFile(const QString &path) {
    QString filePath = path.trimmed();
    if (filePath.startsWith("file:", Qt::CaseInsensitive)) {
        filePath = QUrl(filePath).toLocalFile();
    }

    if (filePath.isEmpty()) {
        setLastError("CSV path is empty.");
        return false;
    }

    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        setLastError(QString("Cannot open CSV: %1").arg(file.errorString()));
        return false;
    }

    QTextStream stream(&file);
    QString headerLine = stream.readLine();
    if (headerLine.isEmpty()) {
        setLastError("CSV header is empty.");
        return false;
    }

    const QStringList header = headerLine.split(',');
    const int dataCols = header.size() - 4;
    if (dataCols <= 0) {
        setLastError("CSV header has no spectrum data.");
        return false;
    }

    QVector<Frame> frames;
    while (!stream.atEnd()) {
        const QString line = stream.readLine().trimmed();
        if (line.isEmpty()) {
            continue;
        }
        const QStringList parts = line.split(',');
        if (parts.size() < 4 + dataCols) {
            continue;
        }

        Frame frame;
        frame.timestamp = parts[0];
        bool okFreq = false;
        bool okSpan = false;
        frame.freqMHz = parts[1].toDouble(&okFreq);
        frame.spanKHz = parts[2].toDouble(&okSpan);
        QVector<float> samples;
        samples.reserve(dataCols);
        for (int i = 0; i < dataCols; ++i) {
            bool ok = false;
            const float value = parts[4 + i].toFloat(&ok);
            if (!ok) {
                samples.clear();
                break;
            }
            samples.append(value);
        }
        if (samples.isEmpty()) {
            continue;
        }
        frame.samples = resample(samples, kSpectrumWidth);
        if (!okFreq || !okSpan) {
            frame.freqMHz = 0.0;
            frame.spanKHz = 0.0;
        }
        frames.append(frame);
    }

    if (frames.isEmpty()) {
        setLastError("CSV contains no valid spectrum rows.");
        return false;
    }

    m_frames = frames;
    m_loaded = true;
    emit loadedChanged();
    emit lineCountChanged();
    if (m_playing) {
        m_playing = false;
        emit playingChanged();
        updateTimer();
    }
    showFrame(0, true);

    return true;
}

void CsvReplay::next() {
    if (!m_loaded || m_frames.isEmpty()) {
        return;
    }
    const int nextIndex = qMin(m_currentIndex + 1, m_frames.size() - 1);
    showFrame(nextIndex, false);
    if (nextIndex >= m_frames.size() - 1 && m_playing) {
        pause();
    }
}

void CsvReplay::prev() {
    if (!m_loaded || m_frames.isEmpty()) {
        return;
    }
    const int prevIndex = qMax(m_currentIndex - 1, 0);
    showFrame(prevIndex, true);
}

void CsvReplay::setIndex(int index) {
    if (!m_loaded || m_frames.isEmpty()) {
        return;
    }
    const int clamped = qBound(0, index, m_frames.size() - 1);
    if (m_playing) {
        pause();
    }
    showFrame(clamped, true);
}

void CsvReplay::play() {
    if (!m_loaded || m_frames.isEmpty()) {
        return;
    }
    if (m_playing) {
        return;
    }
    m_playing = true;
    emit playingChanged();
    updateTimer();
}

void CsvReplay::pause() {
    if (!m_playing) {
        return;
    }
    m_playing = false;
    emit playingChanged();
    updateTimer();
}

void CsvReplay::togglePlay() {
    if (m_playing) {
        pause();
    } else {
        play();
    }
}

void CsvReplay::setSpeed(double speed) {
    const double clamped = qBound(0.1, speed, 10.0);
    if (qFuzzyCompare(clamped, m_speed)) {
        return;
    }
    m_speed = clamped;
    emit speedChanged();
    updateTimer();
}

void CsvReplay::setWaterfallDepth(int depth) {
    const int clamped = qMax(1, depth);
    if (clamped == m_waterfallDepth) {
        return;
    }
    m_waterfallDepth = clamped;
    emit waterfallDepthChanged();
    if (m_loaded && m_currentIndex >= 0) {
        showFrame(m_currentIndex, true);
    }
}

void CsvReplay::showFrame(int index, bool rebuild) {
    if (index < 0 || index >= m_frames.size()) {
        return;
    }
    m_currentIndex = index;
    emit currentIndexChanged();

    const Frame &frame = m_frames[index];
    if (frame.timestamp != m_currentTimestamp) {
        m_currentTimestamp = frame.timestamp;
        emit currentTimestampChanged();
    }
    if (!qFuzzyCompare(frame.freqMHz, m_currentFreqMHz)) {
        m_currentFreqMHz = frame.freqMHz;
        emit currentFreqChanged();
    }
    if (!qFuzzyCompare(frame.spanKHz, m_currentSpanKHz)) {
        m_currentSpanKHz = frame.spanKHz;
        emit currentSpanChanged();
    }

    if (rebuild) {
        QVector<QVector<float>> history;
        const int depth = qMax(1, m_waterfallDepth);
        const int start = qMax(0, index - depth + 1);
        history.reserve(index - start + 1);
        for (int i = start; i <= index; ++i) {
            history.append(m_frames[i].samples);
        }
        emit historyReady(history);
        return;
    }

    emit frameReady(frame.samples);
}

void CsvReplay::setLastError(const QString &errorText) {
    if (m_lastError == errorText) {
        return;
    }
    m_lastError = errorText;
    emit lastErrorChanged();
}

QString CsvReplay::timestampAt(int index) const {
    if (index < 0 || index >= m_frames.size()) {
        return QString();
    }
    return m_frames[index].timestamp;
}

void CsvReplay::updateTimer() {
    if (!m_playing) {
        m_timer.stop();
        return;
    }
    const int interval = qMax(1, int(40.0 / m_speed));
    m_timer.setInterval(interval);
    if (!m_timer.isActive()) {
        m_timer.start();
    }
}

QVector<float> CsvReplay::resample(const QVector<float> &input, int targetSize) {
    if (input.isEmpty() || targetSize <= 0) {
        return QVector<float>();
    }
    if (input.size() == targetSize) {
        return input;
    }

    QVector<float> out(targetSize, 0.0f);
    const int inSize = input.size();
    if (inSize == 1) {
        out.fill(input[0]);
        return out;
    }

    for (int i = 0; i < targetSize; ++i) {
        const float pos = (inSize - 1) * (float(i) / float(targetSize - 1));
        const int idx = int(pos);
        const int idx2 = qMin(idx + 1, inSize - 1);
        const float t = pos - idx;
        out[i] = input[idx] * (1.0f - t) + input[idx2] * t;
    }
    return out;
}

double CsvReplay::getCurrentMaxDbm() const {
    if (!m_loaded || m_currentIndex < 0 || m_currentIndex >= m_frames.size()) {
        return -999.0;
    }
    
    const auto &samples = m_frames[m_currentIndex].samples;
    if (samples.isEmpty()) {
        return -999.0;
    }
    
    float maxVal = samples[0];
    for (float val : samples) {
        if (val > maxVal) {
            maxVal = val;
        }
    }
    return static_cast<double>(maxVal);
}

int CsvReplay::findMaxSignalIndex() const {
    if (!m_loaded || m_frames.isEmpty()) {
        return -1;
    }
    
    int maxIndex = 0;
    double maxDbm = -999.0;
    
    for (int i = 0; i < m_frames.size(); ++i) {
        const auto &samples = m_frames[i].samples;
        if (samples.isEmpty()) continue;
        
        float frameMax = samples[0];
        for (float val : samples) {
            if (val > frameMax) {
                frameMax = val;
            }
        }
        
        if (frameMax > maxDbm) {
            maxDbm = frameMax;
            maxIndex = i;
        }
    }
    
    return maxIndex;
}
