#include "csv_replay.h"

#include <QDir>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QPainter>
#include <QPen>
#include <QFontMetrics>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>
#include <QtGlobal>
#include <QTextStream>
#include <QUrl>

namespace {
constexpr int kSpectrumWidth = 475;
constexpr int kWaterfallDepth = 200;

constexpr QRgb kColors[] = {
    qRgb(0, 0, 0),
    qRgb(0, 0, 128),
    qRgb(0, 255, 255),
    qRgb(0, 255, 0),
    qRgb(255, 255, 0),
    qRgb(255, 128, 0),
    qRgb(255, 0, 0),
    qRgb(255, 255, 255)
};

QRgb lerpColor(QRgb a, QRgb b, float t) {
    const int r = qRed(a) + static_cast<int>((qRed(b) - qRed(a)) * t);
    const int g = qGreen(a) + static_cast<int>((qGreen(b) - qGreen(a)) * t);
    const int bch = qBlue(a) + static_cast<int>((qBlue(b) - qBlue(a)) * t);
    return qRgb(r, g, bch);
}

QRgb mapWaterfallColor(float value) {
    float t = value;
    if (t < 0.0f) {
        t = 0.0f;
    } else if (t > 1.0f) {
        t = 1.0f;
    }

    const int count = static_cast<int>(sizeof(kColors) / sizeof(kColors[0]));
    if (count <= 1) {
        return (count == 1) ? kColors[0] : qRgb(0, 0, 0);
    }

    const float scaled = t * float(count - 1);
    const int idx = qBound(0, int(scaled), count - 2);
    const float local = scaled - float(idx);
    return lerpColor(kColors[idx], kColors[idx + 1], local);
}

QString normalizedPath(const QString &rawPath) {
    QString filePath = rawPath.trimmed();
    if (filePath.startsWith("file:", Qt::CaseInsensitive)) {
        filePath = QUrl(filePath).toLocalFile();
    }
    return filePath;
}
}

CsvReplay::CsvReplay(QObject *parent)
    : QObject(parent),
      m_loaded(false),
      m_currentIndex(-1),
      m_playing(false),
      m_speed(1.0),
      m_currentFreqMHz(0.0),
      m_currentSpanKHz(0.0),
      m_waterfallDepth(kWaterfallDepth),
      m_fileMinDbm(-999.0),
      m_fileMaxDbm(-999.0),
      m_fileAvgDbm(-999.0),
      m_exportImageWidth(0),
      m_exportImageHeight(0),
      m_sourcePointsPerRow(0) {
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

double CsvReplay::fileMinDbm() const {
    return m_fileMinDbm;
}

double CsvReplay::fileMaxDbm() const {
    return m_fileMaxDbm;
}

double CsvReplay::fileAvgDbm() const {
    return m_fileAvgDbm;
}

QString CsvReplay::lastExportStatus() const {
    return m_lastExportStatus;
}

QString CsvReplay::exportPreviewPath() const {
    return m_exportPreviewPath;
}

int CsvReplay::exportImageWidth() const {
    return m_exportImageWidth;
}

int CsvReplay::exportImageHeight() const {
    return m_exportImageHeight;
}

bool CsvReplay::loadFile(const QString &path) {
    const QString filePath = normalizedPath(path);

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
    double minDbm = 0.0;
    double maxDbm = 0.0;
    double sumDbm = 0.0;
    qint64 countDbm = 0;
    bool hasStats = false;
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
        bool okRefLevel = false;
        frame.refLevelDbm = parts[3].toDouble(&okRefLevel);
        if (!okRefLevel) {
            frame.refLevelDbm = 0.0;
        }
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
            if (!hasStats) {
                minDbm = maxDbm = value;
                hasStats = true;
            } else {
                if (value < minDbm) minDbm = value;
                if (value > maxDbm) maxDbm = value;
            }
            sumDbm += value;
            countDbm += 1;
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
    m_loadedCsvPath = QDir::toNativeSeparators(filePath);
    m_exportPreviewPath.clear();
    m_sourcePointsPerRow = dataCols;
    m_exportImageWidth = m_frames.first().samples.size();
    m_exportImageHeight = m_frames.size();
    if (hasStats && countDbm > 0) {
        m_fileMinDbm = minDbm;
        m_fileMaxDbm = maxDbm;
        m_fileAvgDbm = sumDbm / double(countDbm);
    } else {
        m_fileMinDbm = -999.0;
        m_fileMaxDbm = -999.0;
        m_fileAvgDbm = -999.0;
    }
    emit loadedChanged();
    emit lineCountChanged();
    emit fileStatsChanged();
    emit exportPreviewPathChanged();
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

bool CsvReplay::exportWaterfallImage(const QString &path, double dbmMin, double dbmMax) {
    return exportWaterfallImageCropWithMarkers(path, dbmMin, dbmMax, 0.0, 0.0, 1.0, 1.0,
                                               QVariantList(), false, false, 0.0, QString());
}

bool CsvReplay::exportWaterfallImageCrop(const QString &path, double dbmMin, double dbmMax,
                                         double x0Norm, double y0Norm, double x1Norm, double y1Norm) {
    return exportWaterfallImageCropWithMarkers(path, dbmMin, dbmMax, x0Norm, y0Norm, x1Norm, y1Norm,
                                               QVariantList(), false, false, 0.0, QString());
}

bool CsvReplay::exportWaterfallImageWithMarkers(const QString &path, double dbmMin, double dbmMax,
                                                const QVariantList &markers, bool includeMarkers,
                                                bool includeInfo, double centerFreqMHz, const QString &timestampText) {
    return exportWaterfallImageCropWithMarkers(path, dbmMin, dbmMax, 0.0, 0.0, 1.0, 1.0,
                                               markers, includeMarkers, includeInfo, centerFreqMHz, timestampText);
}

bool CsvReplay::exportWaterfallImageCropWithMarkers(const QString &path, double dbmMin, double dbmMax,
                                                    double x0Norm, double y0Norm, double x1Norm, double y1Norm,
                                                    const QVariantList &markers, bool includeMarkers,
                                                    bool includeInfo, double centerFreqMHz, const QString &timestampText) {
    const QString filePath = normalizedPath(path);
    if (filePath.isEmpty()) {
        m_lastExportStatus = "Export failed: empty output path.";
        emit lastExportStatusChanged();
        return false;
    }
    if (!m_loaded || m_frames.isEmpty()) {
        m_lastExportStatus = "Export failed: no CSV loaded.";
        emit lastExportStatusChanged();
        return false;
    }

    QFileInfo outInfo(filePath);
    const QString outDir = outInfo.absolutePath();
    if (!QDir().mkpath(outDir)) {
        m_lastExportStatus = QString("Export failed: cannot create folder '%1'.").arg(outDir);
        emit lastExportStatusChanged();
        return false;
    }

    QImage fullImage = buildWaterfallImage(static_cast<float>(dbmMin), static_cast<float>(dbmMax));
    if (fullImage.isNull()) {
        m_lastExportStatus = "Export failed: invalid source image.";
        emit lastExportStatusChanged();
        return false;
    }
    if (includeMarkers && !markers.isEmpty()) {
        drawMarkersOnImage(fullImage, markers);
    }

    QImage image = cropByNorm(fullImage, x0Norm, y0Norm, x1Norm, y1Norm);
    if (image.isNull()) {
        m_lastExportStatus = "Export failed: invalid crop rectangle.";
        emit lastExportStatusChanged();
        return false;
    }
    if (includeInfo) {
        drawInfoOnImage(image, centerFreqMHz, timestampText);
    }

    bool ok = false;
    const QString suffix = outInfo.suffix().toLower();
    if (suffix == "jpg" || suffix == "jpeg") {
        ok = image.save(filePath, "JPG");
    } else {
        ok = image.save(filePath, "PNG");
    }

    if (!ok) {
        m_lastExportStatus = QString("Export failed: cannot write '%1'.").arg(filePath);
        emit lastExportStatusChanged();
        return false;
    }

    m_lastExportStatus = QString("Export OK: %1 (%2x%3)")
                             .arg(QDir::toNativeSeparators(filePath))
                             .arg(image.width())
                             .arg(image.height());
    emit lastExportStatusChanged();
    return true;
}

void CsvReplay::drawInfoOnImage(QImage &image, double centerFreqMHz, const QString &timestampText) const {
    if (image.isNull()) {
        return;
    }

    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing, false);
    painter.setRenderHint(QPainter::TextAntialiasing, true);
    QFont font = painter.font();
    const int dynamicPx = qBound(12, image.width() / 55, 18);
    font.setPixelSize(dynamicPx);
    painter.setFont(font);
    const QFontMetrics fm(font);

    const QString info = QString("Fc: %1 MHz    Time: %2")
                             .arg(centerFreqMHz, 0, 'f', 6)
                             .arg(timestampText.isEmpty() ? QStringLiteral("--") : timestampText);
    const int padX = 6;
    const int padY = 4;
    const int margin = 8;
    const int maxTextW = qMax(40, image.width() - (margin * 2) - (padX * 2));
    const QString fittedInfo = fm.elidedText(info, Qt::ElideRight, maxTextW);
    const int boxW = qMin(fm.horizontalAdvance(fittedInfo) + padX * 2, qMax(1, image.width() - margin * 2));
    const int boxH = fm.height() + padY * 2;
    const int boxX = qBound(0, margin, qMax(0, image.width() - boxW));
    const int boxY = qBound(0, image.height() - boxH - margin, qMax(0, image.height() - boxH));
    const QRect boxRect(boxX, boxY, qMin(boxW, image.width()), qMin(boxH, image.height()));

    painter.fillRect(boxRect, QColor(0, 0, 0, 190));
    QPen borderPen(QColor("#ffffff"));
    borderPen.setWidth(1);
    painter.setPen(borderPen);
    painter.drawRect(boxRect.adjusted(0, 0, -1, -1));

    painter.setPen(Qt::white);
    painter.drawText(boxRect.x() + padX, boxRect.y() + padY + fm.ascent(), fittedInfo);
}

void CsvReplay::drawMarkersOnImage(QImage &image, const QVariantList &markers) const {
    if (image.isNull() || markers.isEmpty()) {
        return;
    }

    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing, false);
    painter.setRenderHint(QPainter::TextAntialiasing, true);
    const int half = qMax(3, qMin(image.width(), image.height()) / 120);
    QFont font = painter.font();
    font.setPixelSize(12);
    painter.setFont(font);
    const QFontMetrics fm(font);

    for (const QVariant &item : markers) {
        const QVariantMap marker = item.toMap();
        if (marker.isEmpty()) {
            continue;
        }

        bool okX = false;
        bool okFrame = false;
        const double xNorm = marker.value("xNorm").toDouble(&okX);
        const int frameIndex = marker.value("frameIndex").toInt(&okFrame);
        if (!okX || !okFrame) {
            continue;
        }
        if (frameIndex < 0 || frameIndex >= image.height()) {
            continue;
        }

        QColor color(marker.value("color").toString());
        if (!color.isValid()) {
            color = QColor("#00ff66");
        }

        const int x = qBound(0, qRound(xNorm * double(image.width() - 1)), image.width() - 1);
        const int y = image.height() - 1 - frameIndex;

        QPen pen(color);
        pen.setWidth(2);
        painter.setPen(pen);
        painter.drawLine(x - half, y, x + half, y);
        painter.drawLine(x, y - half, x, y + half);

        QStringList lines;
        bool okFreq = false;
        bool okDbm = false;
        const double freq = marker.value("freq").toDouble(&okFreq);
        const double dbm = marker.value("dbm").toDouble(&okDbm);
        const QString timeText = marker.value("time").toString();
        if (okFreq) {
            lines.append(QString("%1 MHz").arg(freq, 0, 'f', 6));
        }
        if (okDbm) {
            lines.append(QString("%1 dBm").arg(dbm, 0, 'f', 1));
        }
        if (!timeText.isEmpty()) {
            lines.append(timeText);
        }
        if (lines.isEmpty()) {
            continue;
        }

        int textWidth = 0;
        for (const QString &line : lines) {
            textWidth = qMax(textWidth, fm.horizontalAdvance(line));
        }
        const int textHeight = lines.size() * fm.height();
        const int padX = 4;
        const int padY = 3;
        const int boxW = textWidth + padX * 2;
        const int boxH = textHeight + padY * 2;

        int boxX = (x > image.width() * 0.6) ? (x - boxW - 6) : (x + 6);
        int boxY = (y > image.height() * 0.6) ? (y - boxH - 6) : (y + 6);
        boxX = qBound(0, boxX, image.width() - boxW);
        boxY = qBound(0, boxY, image.height() - boxH);
        const QRect boxRect(boxX, boxY, boxW, boxH);

        painter.fillRect(boxRect, QColor(0, 0, 0, 190));
        QPen borderPen(color);
        borderPen.setWidth(1);
        painter.setPen(borderPen);
        painter.drawRect(boxRect.adjusted(0, 0, -1, -1));

        painter.setPen(Qt::white);
        int ty = boxY + padY + fm.ascent();
        for (const QString &line : lines) {
            painter.drawText(boxX + padX, ty, line);
            ty += fm.height();
        }
    }
}

bool CsvReplay::exportMetadataJson(const QString &path) {
    const QString filePath = normalizedPath(path);
    if (filePath.isEmpty()) {
        m_lastExportStatus = "Metadata export failed: empty output path.";
        emit lastExportStatusChanged();
        return false;
    }
    if (!m_loaded || m_frames.isEmpty()) {
        m_lastExportStatus = "Metadata export failed: no CSV loaded.";
        emit lastExportStatusChanged();
        return false;
    }

    QFileInfo outInfo(filePath);
    const QString outDir = outInfo.absolutePath();
    if (!QDir().mkpath(outDir)) {
        m_lastExportStatus = QString("Metadata export failed: cannot create folder '%1'.").arg(outDir);
        emit lastExportStatusChanged();
        return false;
    }

    double freqMin = 0.0;
    double freqMax = 0.0;
    double freqSum = 0.0;
    qint64 freqCount = 0;

    double spanMin = 0.0;
    double spanMax = 0.0;
    double spanSum = 0.0;
    qint64 spanCount = 0;

    double refMin = 0.0;
    double refMax = 0.0;
    double refSum = 0.0;
    qint64 refCount = 0;

    auto updateStats = [](double value, qint64 &count, double &sum, double &minV, double &maxV) {
        if (count == 0) {
            minV = maxV = value;
        } else {
            if (value < minV) minV = value;
            if (value > maxV) maxV = value;
        }
        sum += value;
        count += 1;
    };

    for (const Frame &frame : m_frames) {
        updateStats(frame.freqMHz, freqCount, freqSum, freqMin, freqMax);
        updateStats(frame.spanKHz, spanCount, spanSum, spanMin, spanMax);
        updateStats(frame.refLevelDbm, refCount, refSum, refMin, refMax);
    }

    const int replayPoints = m_frames.first().samples.size();
    const int sourcePoints = m_sourcePointsPerRow > 0 ? m_sourcePointsPerRow : replayPoints;

    QJsonObject root;
    root["schema_version"] = QStringLiteral("ic705_qt_metadata_v1");
    root["generated_utc"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
    root["source_csv"] = m_loadedCsvPath;

    QJsonObject capture;
    capture["frames"] = m_frames.size();
    capture["source_points_per_frame"] = sourcePoints;
    capture["replay_points_per_frame"] = replayPoints;
    capture["resampled_for_replay"] = (sourcePoints != replayPoints);
    capture["timestamp_start"] = m_frames.first().timestamp;
    capture["timestamp_end"] = m_frames.last().timestamp;
    root["capture"] = capture;

    QJsonObject freqObj;
    freqObj["start"] = m_frames.first().freqMHz;
    freqObj["end"] = m_frames.last().freqMHz;
    freqObj["min"] = freqMin;
    freqObj["max"] = freqMax;
    freqObj["avg"] = (freqCount > 0) ? (freqSum / double(freqCount)) : 0.0;
    root["frequency_mhz"] = freqObj;

    QJsonObject spanObj;
    spanObj["start"] = m_frames.first().spanKHz;
    spanObj["end"] = m_frames.last().spanKHz;
    spanObj["min"] = spanMin;
    spanObj["max"] = spanMax;
    spanObj["avg"] = (spanCount > 0) ? (spanSum / double(spanCount)) : 0.0;
    root["span_khz"] = spanObj;

    QJsonObject refObj;
    refObj["start"] = m_frames.first().refLevelDbm;
    refObj["end"] = m_frames.last().refLevelDbm;
    refObj["min"] = refMin;
    refObj["max"] = refMax;
    refObj["avg"] = (refCount > 0) ? (refSum / double(refCount)) : 0.0;
    root["ref_level_dbm"] = refObj;

    QJsonObject dbmObj;
    dbmObj["min"] = m_fileMinDbm;
    dbmObj["max"] = m_fileMaxDbm;
    dbmObj["avg"] = m_fileAvgDbm;
    root["dbm_samples"] = dbmObj;

    QFile outFile(filePath);
    if (!outFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        m_lastExportStatus = QString("Metadata export failed: cannot write '%1'.").arg(filePath);
        emit lastExportStatusChanged();
        return false;
    }
    const QJsonDocument doc(root);
    const qint64 written = outFile.write(doc.toJson(QJsonDocument::Indented));
    outFile.close();
    if (written <= 0) {
        m_lastExportStatus = QString("Metadata export failed: write error '%1'.").arg(filePath);
        emit lastExportStatusChanged();
        return false;
    }

    m_lastExportStatus = QString("Metadata export OK: %1").arg(QDir::toNativeSeparators(filePath));
    emit lastExportStatusChanged();
    return true;
}

bool CsvReplay::generateExportPreview(double dbmMin, double dbmMax, int maxWidth, int maxHeight) {
    if (!m_loaded || m_frames.isEmpty()) {
        m_lastExportStatus = "Preview failed: no CSV loaded.";
        emit lastExportStatusChanged();
        return false;
    }

    const QImage fullImage = buildWaterfallImage(static_cast<float>(dbmMin), static_cast<float>(dbmMax));
    if (fullImage.isNull()) {
        m_lastExportStatus = "Preview failed: cannot build image.";
        emit lastExportStatusChanged();
        return false;
    }

    const int targetW = qMax(64, maxWidth);
    const int targetH = qMax(64, maxHeight);
    const QImage preview = fullImage.scaled(targetW, targetH, Qt::KeepAspectRatio, Qt::FastTransformation);
    const QString tempFile = QDir::toNativeSeparators(
        QDir(QStandardPaths::writableLocation(QStandardPaths::TempLocation))
            .filePath("ic705_qt_export_preview.png"));
    if (!preview.save(tempFile, "PNG")) {
        m_lastExportStatus = "Preview failed: cannot write temp preview.";
        emit lastExportStatusChanged();
        return false;
    }

    m_exportPreviewPath = QUrl::fromLocalFile(tempFile).toString();
    m_exportImageWidth = fullImage.width();
    m_exportImageHeight = fullImage.height();
    emit exportPreviewPathChanged();
    m_lastExportStatus = QString("Preview ready: %1x%2").arg(m_exportImageWidth).arg(m_exportImageHeight);
    emit lastExportStatusChanged();
    return true;
}

QImage CsvReplay::buildWaterfallImage(float dbmMin, float dbmMax) const {
    if (!m_loaded || m_frames.isEmpty()) {
        return QImage();
    }
    const int width = m_frames.first().samples.size();
    const int height = m_frames.size();
    if (width <= 0 || height <= 0) {
        return QImage();
    }

    float minValue = dbmMin;
    float maxValue = dbmMax;
    if (maxValue - minValue < 1.0f) {
        maxValue = minValue + 1.0f;
    }
    const float range = maxValue - minValue;

    QImage image(width, height, QImage::Format_ARGB32);
    image.fill(qRgb(0, 0, 0));
    for (int frameIndex = 0; frameIndex < height; ++frameIndex) {
        const int y = height - 1 - frameIndex;
        QRgb *row = reinterpret_cast<QRgb *>(image.scanLine(y));
        const QVector<float> &samples = m_frames[frameIndex].samples;
        for (int x = 0; x < width; ++x) {
            const float v = (samples[x] - minValue) / range;
            row[x] = mapWaterfallColor(v);
        }
    }
    return image;
}

QImage CsvReplay::cropByNorm(const QImage &source, double x0Norm, double y0Norm, double x1Norm, double y1Norm) const {
    if (source.isNull()) {
        return QImage();
    }
    const double x0 = qBound(0.0, qMin(x0Norm, x1Norm), 1.0);
    const double y0 = qBound(0.0, qMin(y0Norm, y1Norm), 1.0);
    const double x1 = qBound(0.0, qMax(x0Norm, x1Norm), 1.0);
    const double y1 = qBound(0.0, qMax(y0Norm, y1Norm), 1.0);

    int left = static_cast<int>(x0 * source.width());
    int top = static_cast<int>(y0 * source.height());
    int right = static_cast<int>(x1 * source.width());
    int bottom = static_cast<int>(y1 * source.height());

    left = qBound(0, left, source.width() - 1);
    top = qBound(0, top, source.height() - 1);
    right = qBound(left + 1, right, source.width());
    bottom = qBound(top + 1, bottom, source.height());

    const QRect rect(left, top, right - left, bottom - top);
    if (!rect.isValid() || rect.width() <= 0 || rect.height() <= 0) {
        return QImage();
    }
    return source.copy(rect);
}
