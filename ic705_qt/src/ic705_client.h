#pragma once

#include <QObject>
#include <QByteArray>
#include <QHostAddress>
#include <QUdpSocket>
#include <QTimer>

class IC705Client : public QObject {
    Q_OBJECT

public:
    struct Params {
        QString radioIp;
        QString username;
        QString password;
        QString radioName;
        QByteArray radioMac;
        QByteArray radioGuid;
        quint8 civTo = 0xA4;
        quint8 civFrom = 0xE0;
        QString compName = "PC-wfview";
    };

    explicit IC705Client(QObject *parent = nullptr);

    bool connectToRadio(const Params &params, int timeoutMs, QString *error = nullptr);
    void close();
    bool connected() const;

    void sendCivFrame(const QByteArray &payload);
    void sendCivCmd(quint8 cmd, const QByteArray &data = QByteArray());

signals:
    void connectedChanged(bool connected);
    void statusTextChanged(const QString &text);
    void civFrameReceived(const QByteArray &payload);

private slots:
    void onCtrlReadyRead();
    void onCivReadyRead();
    void onIdleTimeout();
    void onTokenTimeout();

private:
    struct UdpStream {
        QUdpSocket *socket = nullptr;
        quint16 localPort = 0;
        quint32 myId = 0;
        quint32 remoteId = 0;
        quint16 sendSeq = 1;
    };

    bool openControl(QString *error);
    bool controlHandshake(int timeoutMs, QString *error);
    bool openCiv(QString *error);
    bool civHandshake(int timeoutMs, QString *error);

    void sendControl(UdpStream &stream, quint16 pktType, bool tracked, quint16 seqUntracked, quint16 port);
    void sendLogin();
    void sendToken(quint8 magic);
    void sendRequestStream();
    void sendOpenClose(bool open);

    void handlePing(UdpStream &stream, const QByteArray &data, quint16 port);
    void updateStatus(const QString &text);

    static QByteArray passcode(const QString &text);
    static quint32 computeMyId(const QHostAddress &localAddr, quint16 localPort);
    static bool parseHeader(const QByteArray &data, quint32 &size, quint16 &ptype, quint16 &pseq,
                            quint32 &sentId, quint32 &remoteId);
    static QHostAddress pickLocalAddress(const QHostAddress &remoteAddr, quint16 remotePort);
    static bool reserveTwoUdpPorts(const QHostAddress &localAddr, quint16 &port1, quint16 &port2);
    static void putU16LE(QByteArray &buf, int offset, quint16 value);
    static void putU32LE(QByteArray &buf, int offset, quint32 value);
    static void putU16BE(QByteArray &buf, int offset, quint16 value);
    static void putU32BE(QByteArray &buf, int offset, quint32 value);
    static quint16 getU16LE(const QByteArray &buf, int offset);
    static quint32 getU32LE(const QByteArray &buf, int offset);
    static quint16 getU16BE(const QByteArray &buf, int offset);
    static QByteArray buildHeader(quint32 totalLen, quint16 pktType, quint32 myId, quint32 remoteId);
    static void setExternalSeq(UdpStream &stream, QByteArray &buf);

    Params m_params;
    bool m_connected = false;
    QString m_statusText;

    QHostAddress m_radioAddr;
    QHostAddress m_localAddr;

    UdpStream m_ctrlStream;
    UdpStream m_civStream;
    QUdpSocket m_ctrlSocket;
    QUdpSocket m_civSocket;

    quint16 m_civLocalPort = 0;
    quint16 m_audioLocalPort = 0;
    quint16 m_civRemotePort = 0;
    quint16 m_authSeq = 0x30;
    quint16 m_tokRequest = 0;
    quint32 m_token = 0;
    quint16 m_civSendSeqB = 0;

    QTimer m_idleTimer;
    QTimer m_tokenTimer;
};
