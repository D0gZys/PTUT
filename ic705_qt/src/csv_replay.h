#pragma once

#include <QObject>
#include <QImage>
#include <QTimer>
#include <QVariantList>
#include <QVector>

class CsvReplay : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool loaded READ loaded NOTIFY loadedChanged)
    Q_PROPERTY(int lineCount READ lineCount NOTIFY lineCountChanged)
    Q_PROPERTY(int currentIndex READ currentIndex NOTIFY currentIndexChanged)
    Q_PROPERTY(QString currentTimestamp READ currentTimestamp NOTIFY currentTimestampChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(bool playing READ playing NOTIFY playingChanged)
    Q_PROPERTY(double speed READ speed NOTIFY speedChanged)
    Q_PROPERTY(double currentFreqMHz READ currentFreqMHz NOTIFY currentFreqChanged)
    Q_PROPERTY(double currentSpanKHz READ currentSpanKHz NOTIFY currentSpanChanged)
    Q_PROPERTY(int waterfallDepth READ waterfallDepth WRITE setWaterfallDepth NOTIFY waterfallDepthChanged)
    Q_PROPERTY(double fileMinDbm READ fileMinDbm NOTIFY fileStatsChanged)
    Q_PROPERTY(double fileMaxDbm READ fileMaxDbm NOTIFY fileStatsChanged)
    Q_PROPERTY(double fileAvgDbm READ fileAvgDbm NOTIFY fileStatsChanged)
    Q_PROPERTY(QString lastExportStatus READ lastExportStatus NOTIFY lastExportStatusChanged)
    Q_PROPERTY(QString exportPreviewPath READ exportPreviewPath NOTIFY exportPreviewPathChanged)
    Q_PROPERTY(int exportImageWidth READ exportImageWidth NOTIFY exportPreviewPathChanged)
    Q_PROPERTY(int exportImageHeight READ exportImageHeight NOTIFY exportPreviewPathChanged)

public:
    explicit CsvReplay(QObject *parent = nullptr);

    bool loaded() const;
    int lineCount() const;
    int currentIndex() const;
    QString currentTimestamp() const;
    QString lastError() const;
    bool playing() const;
    double speed() const;
    double currentFreqMHz() const;
    double currentSpanKHz() const;
    int waterfallDepth() const;
    double fileMinDbm() const;
    double fileMaxDbm() const;
    double fileAvgDbm() const;
    QString lastExportStatus() const;
    QString exportPreviewPath() const;
    int exportImageWidth() const;
    int exportImageHeight() const;

    Q_INVOKABLE bool loadFile(const QString &path);
    Q_INVOKABLE void next();
    Q_INVOKABLE void prev();
    Q_INVOKABLE void setIndex(int index);
    Q_INVOKABLE void play();
    Q_INVOKABLE void pause();
    Q_INVOKABLE void togglePlay();
    Q_INVOKABLE void setSpeed(double speed);
    Q_INVOKABLE void setWaterfallDepth(int depth);
    Q_INVOKABLE QString timestampAt(int index) const;
    Q_INVOKABLE double getCurrentMaxDbm() const;
    Q_INVOKABLE int findMaxSignalIndex() const;
    Q_INVOKABLE bool exportWaterfallImage(const QString &path, double dbmMin, double dbmMax);
    Q_INVOKABLE bool exportWaterfallImageCrop(const QString &path, double dbmMin, double dbmMax,
                                              double x0Norm, double y0Norm, double x1Norm, double y1Norm);
    Q_INVOKABLE bool exportWaterfallImageWithMarkers(const QString &path, double dbmMin, double dbmMax,
                                                     const QVariantList &markers, bool includeMarkers,
                                                     bool includeInfo, double centerFreqMHz, const QString &timestampText);
    Q_INVOKABLE bool exportWaterfallImageCropWithMarkers(const QString &path, double dbmMin, double dbmMax,
                                                         double x0Norm, double y0Norm, double x1Norm, double y1Norm,
                                                         const QVariantList &markers, bool includeMarkers,
                                                         bool includeInfo, double centerFreqMHz, const QString &timestampText);
    Q_INVOKABLE bool exportMetadataJson(const QString &path);
    Q_INVOKABLE bool generateExportPreview(double dbmMin, double dbmMax, int maxWidth, int maxHeight);

signals:
    void loadedChanged();
    void lineCountChanged();
    void currentIndexChanged();
    void currentTimestampChanged();
    void lastErrorChanged();
    void playingChanged();
    void speedChanged();
    void currentFreqChanged();
    void currentSpanChanged();
    void waterfallDepthChanged();
    void fileStatsChanged();
    void lastExportStatusChanged();
    void exportPreviewPathChanged();
    void frameReady(const QVector<float> &samples);
    void historyReady(const QVector<QVector<float>> &frames);

private:
    struct Frame {
        QString timestamp;
        double freqMHz;
        double spanKHz;
        double refLevelDbm;
        QVector<float> samples;
    };

    void showFrame(int index, bool rebuild);
    void setLastError(const QString &errorText);
    void updateTimer();
    static QVector<float> resample(const QVector<float> &input, int targetSize);
    QImage buildWaterfallImage(float dbmMin, float dbmMax) const;
    QImage cropByNorm(const QImage &source, double x0Norm, double y0Norm, double x1Norm, double y1Norm) const;
    void drawMarkersOnImage(QImage &image, const QVariantList &markers) const;
    void drawInfoOnImage(QImage &image, double centerFreqMHz, const QString &timestampText) const;

    QVector<Frame> m_frames;
    bool m_loaded;
    int m_currentIndex;
    QString m_currentTimestamp;
    QString m_lastError;
    QString m_lastExportStatus;
    QString m_loadedCsvPath;
    QString m_exportPreviewPath;
    int m_exportImageWidth;
    int m_exportImageHeight;
    int m_sourcePointsPerRow;
    QTimer m_timer;
    bool m_playing;
    double m_speed;
    double m_currentFreqMHz;
    double m_currentSpanKHz;
    int m_waterfallDepth;
    double m_fileMinDbm;
    double m_fileMaxDbm;
    double m_fileAvgDbm;
};
