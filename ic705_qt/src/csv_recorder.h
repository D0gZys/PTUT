#pragma once

#include <QObject>
#include <QFile>
#include <QQueue>
#include <QString>
#include <QVector>

class CsvRecorder : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool recording READ recording NOTIFY recordingChanged)
    Q_PROPERTY(bool triggerEnabled READ triggerEnabled WRITE setTriggerEnabled NOTIFY triggerEnabledChanged)
    Q_PROPERTY(double triggerThreshold READ triggerThreshold WRITE setTriggerThreshold NOTIFY triggerThresholdChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusTextChanged)

public:
    explicit CsvRecorder(QObject *parent = nullptr);

    bool recording() const;
    bool triggerEnabled() const;
    double triggerThreshold() const;
    QString statusText() const;

    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void toggle();
    Q_INVOKABLE void setTriggerEnabled(bool enabled);
    Q_INVOKABLE void setTriggerThreshold(double value);
    Q_INVOKABLE void setCurrentFreqMHz(double value);
    Q_INVOKABLE void setCurrentSpanKHz(double value);
    Q_INVOKABLE void setRefLevel(int value);

public slots:
    void pushSamples(const QVector<float> &samples);

signals:
    void recordingChanged();
    void triggerEnabledChanged();
    void triggerThresholdChanged();
    void statusTextChanged();

private:
    struct Frame {
        QString timestamp;
        double freqMHz;
        double spanKHz;
        int refLevel;
        QVector<float> samples;
    };

    bool openCsv(bool triggerTemp);
    void closeCsv(bool finalizeTrigger);
    void writeHeader(int sampleCount);
    void writeFrame(const Frame &frame);
    QString makeDayFolder() const;
    QString nowTimestamp() const;
    void updateStatus(const QString &text);
    void enqueuePreBuffer(const Frame &frame);

    bool m_recording;
    bool m_triggerEnabled;
    bool m_aboveThreshold;
    double m_triggerThreshold;
    double m_triggerMaxDbm;
    int m_triggerCount;
    int m_postRemaining;
    int m_linesWritten;

    double m_freqMHz;
    double m_spanKHz;
    int m_refLevel;

    QFile m_file;
    QString m_filePath;
    QString m_statusText;
    int m_sampleCount;
    bool m_headerWritten;

    QQueue<Frame> m_preBuffer;
};
