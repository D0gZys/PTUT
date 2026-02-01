#pragma once

#include <QObject>
#include <QByteArray>
#include <QTimer>
#include <QVector>

#include "ic705_client.h"

class CivClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusTextChanged)
    Q_PROPERTY(double freqMHz READ freqMHz NOTIFY freqChanged)
    Q_PROPERTY(int refLevel READ refLevel NOTIFY refLevelChanged)

public:
    explicit CivClient(QObject *parent = nullptr);

    bool connected() const;
    QString statusText() const;
    double freqMHz() const;
    int refLevel() const;

    Q_INVOKABLE void connectToDefault();
    Q_INVOKABLE void connectWithParams(const QString &ip,
                                       const QString &username,
                                       const QString &password,
                                       const QString &radioName,
                                       const QString &radioMac);
    Q_INVOKABLE void disconnectFromHost();

signals:
    void connectedChanged();
    void statusTextChanged();
    void freqChanged();
    void refLevelChanged();
    void spectrumReady(const QVector<float> &samples);

private:
    void onPollTimeout();

    void updateStatus(const QString &text);
    void processMessage(const QByteArray &msg);

    static double decodeFrequencyBcd(const QByteArray &data);
    static int decodeRefLevel(const QByteArray &msg);
    static QVector<float> resample(const QVector<float> &input, int targetSize);
    static QByteArray parseMacBytes(const QString &text, bool *ok);

    IC705Client m_client;
    QTimer m_pollTimer;

    bool m_connected;
    QString m_statusText;
    double m_freqMHz;
    int m_refLevel;
};
