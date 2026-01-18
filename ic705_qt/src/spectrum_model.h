#pragma once

#include <QObject>
#include <QTimer>
#include <QVector>

class SpectrumModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(float dbmMin READ dbmMin NOTIFY rangeChanged)
    Q_PROPERTY(float dbmMax READ dbmMax NOTIFY rangeChanged)
public:
    explicit SpectrumModel(QObject *parent = nullptr);

    const QVector<float> &samples() const;
    float dbmMin() const;
    float dbmMax() const;

    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    void setSamples(const QVector<float> &samples);

signals:
    void samplesChanged();
    void rangeChanged();

private:
    void generateTestData();

    QTimer m_timer;
    QVector<float> m_samples;
    float m_phase;
    float m_dbmMin;
    float m_dbmMax;
};
