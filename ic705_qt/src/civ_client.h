#pragma once

#include <QObject>
#include <QByteArray>
#include <QTcpSocket>
#include <QTimer>
#include <QVector>

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
    Q_INVOKABLE void disconnectFromHost();

signals:
    void connectedChanged();
    void statusTextChanged();
    void freqChanged();
    void refLevelChanged();
    void spectrumReady(const QVector<float> &samples);

private:
    void onConnected();
    void onDisconnected();
    void onReadyRead();
    void onErrorOccurred(QAbstractSocket::SocketError error);
    void onPollTimeout();

    void updateStatus(const QString &text);
    void processMessage(const QByteArray &msg);
    QList<QByteArray> extractMessages(QByteArray &buffer);

    static double decodeFrequencyBcd(const QByteArray &data);
    static int decodeRefLevel(const QByteArray &msg);
    static QVector<float> resample(const QVector<float> &input, int targetSize);
    static QByteArray buildCivFrame(quint8 cmd, quint8 subCmd = 0x00, const QByteArray &payload = QByteArray());

    QTcpSocket m_socket;
    QTimer m_pollTimer;
    QByteArray m_buffer;

    bool m_connected;
    QString m_statusText;
    double m_freqMHz;
    int m_refLevel;
};
