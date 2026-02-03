#pragma once

#include <QObject>
#include <QTimer>
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
    void frameReady(const QVector<float> &samples);
    void historyReady(const QVector<QVector<float>> &frames);

private:
    struct Frame {
        QString timestamp;
        double freqMHz;
        double spanKHz;
        QVector<float> samples;
    };

    void showFrame(int index, bool rebuild);
    void setLastError(const QString &errorText);
    void updateTimer();
    static QVector<float> resample(const QVector<float> &input, int targetSize);

    QVector<Frame> m_frames;
    bool m_loaded;
    int m_currentIndex;
    QString m_currentTimestamp;
    QString m_lastError;
    QTimer m_timer;
    bool m_playing;
    double m_speed;
    double m_currentFreqMHz;
    double m_currentSpanKHz;
    int m_waterfallDepth;
};
