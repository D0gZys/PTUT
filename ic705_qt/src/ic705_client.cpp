#include "ic705_client.h"

#include <QElapsedTimer>
#include <QRandomGenerator>
#include <QVariant>
#include <QtEndian>
#include <cstring>

namespace {
constexpr quint16 CONTROL_PORT = 50001;
constexpr int CONTROL_SIZE = 0x10;
constexpr int PING_SIZE = 0x15;
constexpr int OPENCLOSE_SIZE = 0x16;
constexpr int LOGIN_SIZE = 0x80;
constexpr int LOGIN_RESPONSE_SIZE = 0x60;
constexpr int TOKEN_SIZE = 0x40;
constexpr int STATUS_SIZE = 0x50;
constexpr int CONNINFO_SIZE = 0x90;

constexpr double AREYOUTHERE_PERIOD_S = 0.5;
constexpr double IDLE_PERIOD_S = 0.1;
constexpr double TOKEN_RENEWAL_S = 60.0;
} // namespace

IC705Client::IC705Client(QObject *parent)
    : QObject(parent) {
    connect(&m_ctrlSocket, &QUdpSocket::readyRead, this, &IC705Client::onCtrlReadyRead);
    connect(&m_civSocket, &QUdpSocket::readyRead, this, &IC705Client::onCivReadyRead);

    m_idleTimer.setInterval(int(IDLE_PERIOD_S * 1000));
    m_idleTimer.setTimerType(Qt::CoarseTimer);
    connect(&m_idleTimer, &QTimer::timeout, this, &IC705Client::onIdleTimeout);

    m_tokenTimer.setInterval(int(TOKEN_RENEWAL_S * 1000));
    m_tokenTimer.setTimerType(Qt::CoarseTimer);
    connect(&m_tokenTimer, &QTimer::timeout, this, &IC705Client::onTokenTimeout);
}

bool IC705Client::connectToRadio(const Params &params, int timeoutMs, QString *error) {
    if (m_connected) {
        return true;
    }
    close();
    m_params = params;
    m_radioAddr = QHostAddress(params.radioIp);
    if (m_radioAddr.isNull()) {
        if (error) {
            *error = "Invalid radio IP.";
        }
        return false;
    }

    if (!openControl(error)) {
        return false;
    }

    if (!controlHandshake(timeoutMs, error)) {
        close();
        return false;
    }

    if (!openCiv(error)) {
        close();
        return false;
    }

    if (!civHandshake(10000, error)) {
        close();
        return false;
    }

    m_idleTimer.start();
    m_tokenTimer.start();
    m_connected = true;
    emit connectedChanged(true);
    updateStatus("Connected");
    return true;
}

void IC705Client::close() {
    m_idleTimer.stop();
    m_tokenTimer.stop();
    if (m_connected && m_ctrlStream.socket && m_ctrlStream.remoteId != 0) {
        if (m_token != 0) {
            sendToken(0x01);
        }
        sendControl(m_ctrlStream, 0x05, false, 0x0000, CONTROL_PORT);
        m_ctrlStream.socket->flush();
        m_ctrlStream.socket->waitForBytesWritten(100);
    }
    if (m_connected && m_civStream.socket && m_civRemotePort != 0 && m_civStream.remoteId != 0) {
        sendOpenClose(false);
        sendControl(m_civStream, 0x05, false, 0x0000, m_civRemotePort);
        m_civStream.socket->flush();
        m_civStream.socket->waitForBytesWritten(100);
    }
    if (m_ctrlSocket.isOpen()) {
        m_ctrlSocket.close();
    }
    if (m_civSocket.isOpen()) {
        m_civSocket.close();
    }
    m_ctrlStream = UdpStream();
    m_civStream = UdpStream();
    m_civRemotePort = 0;
    m_civLocalPort = 0;
    m_audioLocalPort = 0;
    m_civSendSeqB = 0;
    m_authSeq = 0x30;
    m_tokRequest = 0;
    m_token = 0;
    if (m_connected) {
        m_connected = false;
        emit connectedChanged(false);
    }
    updateStatus("Disconnected");
}

bool IC705Client::connected() const {
    return m_connected;
}

void IC705Client::sendCivFrame(const QByteArray &payload) {
    if (!m_civStream.socket || m_civRemotePort == 0) {
        return;
    }
    QByteArray hdr(PING_SIZE, char(0));
    const quint32 totalLen = quint32(PING_SIZE + payload.size());
    QByteArray base = buildHeader(totalLen, 0, m_civStream.myId, m_civStream.remoteId);
    hdr.replace(0, CONTROL_SIZE, base.left(CONTROL_SIZE));
    hdr[0x10] = char(0xC1);
    putU16LE(hdr, 0x11, quint16(payload.size()));
    putU16BE(hdr, 0x13, m_civSendSeqB);
    m_civSendSeqB = quint16(m_civSendSeqB + 1);

    QByteArray pkt = hdr + payload;
    setExternalSeq(m_civStream, pkt);
    m_civStream.socket->writeDatagram(pkt, m_radioAddr, m_civRemotePort);
}

void IC705Client::sendCivCmd(quint8 cmd, const QByteArray &data) {
    QByteArray frame;
    frame.append(char(0xFE));
    frame.append(char(0xFE));
    frame.append(char(m_params.civTo));
    frame.append(char(m_params.civFrom));
    frame.append(char(cmd));
    if (!data.isEmpty()) {
        frame.append(data);
    }
    frame.append(char(0xFD));
    sendCivFrame(frame);
}

void IC705Client::onCtrlReadyRead() {
    if (!m_connected) {
        return;
    }
    while (m_ctrlSocket.hasPendingDatagrams()) {
        QByteArray data;
        data.resize(int(m_ctrlSocket.pendingDatagramSize()));
        m_ctrlSocket.readDatagram(data.data(), data.size(), nullptr, nullptr);
        if (data.size() == PING_SIZE) {
            handlePing(m_ctrlStream, data, CONTROL_PORT);
            continue;
        }
        if (data.size() == CONTROL_SIZE) {
            quint32 size = 0;
            quint16 ptype = 0;
            quint16 pseq = 0;
            quint32 sentId = 0;
            quint32 remoteId = 0;
            if (parseHeader(data, size, ptype, pseq, sentId, remoteId)) {
                if (ptype == 0x04 || ptype == 0x06) {
                    m_ctrlStream.remoteId = sentId;
                }
            }
        }
    }
}

void IC705Client::onCivReadyRead() {
    if (!m_connected) {
        return;
    }
    while (m_civSocket.hasPendingDatagrams()) {
        QByteArray data;
        data.resize(int(m_civSocket.pendingDatagramSize()));
        m_civSocket.readDatagram(data.data(), data.size(), nullptr, nullptr);
        if (data.size() == PING_SIZE) {
            handlePing(m_civStream, data, m_civRemotePort);
            continue;
        }
        if (data.size() == CONTROL_SIZE) {
            quint32 size = 0;
            quint16 ptype = 0;
            quint16 pseq = 0;
            quint32 sentId = 0;
            quint32 remoteId = 0;
            if (parseHeader(data, size, ptype, pseq, sentId, remoteId)) {
                if (ptype == 0x04 || ptype == 0x06) {
                    m_civStream.remoteId = sentId;
                }
            }
            continue;
        }
        if (data.size() > PING_SIZE && quint8(data[0x10]) == 0xC1) {
            const QByteArray payload = data.mid(0x15);
            emit civFrameReceived(payload);
        }
    }
}

void IC705Client::onIdleTimeout() {
    if (!m_connected || !m_ctrlStream.socket) {
        return;
    }
    sendControl(m_ctrlStream, 0x00, true, 0, CONTROL_PORT);
}

void IC705Client::onTokenTimeout() {
    if (!m_connected || !m_ctrlStream.socket) {
        return;
    }
    sendToken(0x05);
}

bool IC705Client::openControl(QString *error) {
    if (m_ctrlSocket.state() != QAbstractSocket::UnconnectedState) {
        m_ctrlSocket.close();
    }
    m_localAddr = pickLocalAddress(m_radioAddr, CONTROL_PORT);
    if (m_localAddr.isNull()) {
        if (error) {
            *error = "Failed to pick local address.";
        }
        return false;
    }

    if (!m_ctrlSocket.bind(m_localAddr, 0)) {
        if (error) {
            *error = "Failed to bind control socket.";
        }
        return false;
    }
    m_ctrlSocket.setSocketOption(QAbstractSocket::LowDelayOption, QVariant(1));
    m_ctrlStream.socket = &m_ctrlSocket;
    m_ctrlStream.localPort = m_ctrlSocket.localPort();
    m_ctrlStream.myId = computeMyId(m_localAddr, m_ctrlStream.localPort);
    m_ctrlStream.remoteId = 0;
    m_ctrlStream.sendSeq = 1;
    return true;
}

bool IC705Client::controlHandshake(int timeoutMs, QString *error) {
    if (!reserveTwoUdpPorts(m_localAddr, m_civLocalPort, m_audioLocalPort)) {
        if (error) {
            *error = "Failed to reserve UDP ports.";
        }
        return false;
    }

    QElapsedTimer timer;
    timer.start();
    qint64 nextAyt = 0;
    qint64 nextIdle = 0;
    qint64 nextToken = 0;
    bool connected = false;
    bool authenticated = false;
    bool streamRequested = false;

    while (timer.elapsed() < timeoutMs) {
        const qint64 now = timer.elapsed();
        if (!connected && now >= nextAyt) {
            sendControl(m_ctrlStream, 0x03, false, 0x0000, CONTROL_PORT);
            nextAyt = now + qint64(AREYOUTHERE_PERIOD_S * 1000);
        }
        if (connected && now >= nextIdle) {
            sendControl(m_ctrlStream, 0x00, true, 0, CONTROL_PORT);
            nextIdle = now + qint64(IDLE_PERIOD_S * 1000);
        }
        if (authenticated && now >= nextToken) {
            sendToken(0x05);
            nextToken = now + qint64(TOKEN_RENEWAL_S * 1000);
        }

        if (!m_ctrlSocket.waitForReadyRead(50)) {
            continue;
        }
        while (m_ctrlSocket.hasPendingDatagrams()) {
            QByteArray data;
            data.resize(int(m_ctrlSocket.pendingDatagramSize()));
            m_ctrlSocket.readDatagram(data.data(), data.size(), nullptr, nullptr);

            if (data.size() == PING_SIZE) {
                handlePing(m_ctrlStream, data, CONTROL_PORT);
                continue;
            }

            quint32 size = 0;
            quint16 ptype = 0;
            quint16 pseq = 0;
            quint32 sentId = 0;
            quint32 remoteId = 0;
            if (data.size() >= CONTROL_SIZE && parseHeader(data, size, ptype, pseq, sentId, remoteId)) {
                if (data.size() == CONTROL_SIZE) {
                    if (ptype == 0x04) {
                        m_ctrlStream.remoteId = sentId;
                        connected = true;
                        sendControl(m_ctrlStream, 0x06, false, 0x0001, CONTROL_PORT);
                        continue;
                    }
                    if (ptype == 0x06) {
                        sendLogin();
                        continue;
                    }
                }
            }

            if (data.size() == LOGIN_RESPONSE_SIZE) {
                const quint32 err = getU32LE(data, 0x30);
                const quint16 tokReq = getU16LE(data, 0x1A);
                const quint32 token = getU32LE(data, 0x1C);
                if (err == 0xFEFFFFFFu) {
                    if (error) {
                        *error = "Invalid username/password.";
                    }
                    return false;
                }
                if (!authenticated && tokReq == m_tokRequest) {
                    m_token = token;
                    authenticated = true;
                    sendToken(0x02);
                    sendToken(0x05);
                    nextToken = now + qint64(TOKEN_RENEWAL_S * 1000);
                }
                continue;
            }

            if (data.size() == TOKEN_SIZE) {
                const quint8 requestReply = quint8(data[0x14]);
                const quint8 requestType = quint8(data[0x15]);
                const quint32 response = getU32LE(data, 0x30);
                if (requestType == 0x05 && requestReply == 0x02 && ptype != 0x01) {
                    if (response == 0x00000000u) {
                        if (!streamRequested) {
                            sendRequestStream();
                            streamRequested = true;
                        }
                    } else if (response == 0xFFFFFFFFu) {
                        m_ctrlStream.remoteId = sentId;
                        m_tokRequest = getU16LE(data, 0x1A);
                        m_token = getU32LE(data, 0x1C);
                        sendRequestStream();
                        streamRequested = true;
                    }
                }
                continue;
            }

            if (data.size() == STATUS_SIZE) {
                const quint32 err = getU32LE(data, 0x30);
                const quint8 disc = quint8(data[0x40]);
                const quint16 civPort = getU16BE(data, 0x42);
                if (err == 0xFFFFFFFFu) {
                    if (error) {
                        *error = "Connection failed (status error).";
                    }
                    return false;
                }
                if (err == 0x00000000u && disc == 0x01) {
                    if (error) {
                        *error = "Radio reports disconnected.";
                    }
                    return false;
                }
                m_civRemotePort = civPort;
                return true;
            }
        }
    }

    if (error) {
        *error = "Timeout during control handshake.";
    }
    return false;
}

bool IC705Client::openCiv(QString *error) {
    if (m_civSocket.state() != QAbstractSocket::UnconnectedState) {
        m_civSocket.close();
    }
    if (!m_civSocket.bind(m_localAddr, m_civLocalPort)) {
        if (error) {
            *error = "Failed to bind CIV socket.";
        }
        return false;
    }
    m_civSocket.setSocketOption(QAbstractSocket::LowDelayOption, QVariant(1));
    m_civStream.socket = &m_civSocket;
    m_civStream.localPort = m_civLocalPort;
    m_civStream.myId = computeMyId(m_localAddr, m_civLocalPort);
    m_civStream.remoteId = 0;
    m_civStream.sendSeq = 1;
    return true;
}

bool IC705Client::civHandshake(int timeoutMs, QString *error) {
    QElapsedTimer timer;
    timer.start();
    qint64 nextAyt = 0;

    while (timer.elapsed() < timeoutMs) {
        const qint64 now = timer.elapsed();
        if (now >= nextAyt) {
            sendControl(m_civStream, 0x03, false, 0x0000, m_civRemotePort);
            nextAyt = now + qint64(AREYOUTHERE_PERIOD_S * 1000);
        }

        if (!m_civSocket.waitForReadyRead(50)) {
            continue;
        }
        while (m_civSocket.hasPendingDatagrams()) {
            QByteArray data;
            data.resize(int(m_civSocket.pendingDatagramSize()));
            m_civSocket.readDatagram(data.data(), data.size(), nullptr, nullptr);

            if (data.size() == PING_SIZE) {
                handlePing(m_civStream, data, m_civRemotePort);
                continue;
            }

            if (data.size() == CONTROL_SIZE) {
                quint32 size = 0;
                quint16 ptype = 0;
                quint16 pseq = 0;
                quint32 sentId = 0;
                quint32 remoteId = 0;
                if (parseHeader(data, size, ptype, pseq, sentId, remoteId)) {
                    if (ptype == 0x04) {
                        m_civStream.remoteId = sentId;
                        sendControl(m_civStream, 0x06, false, 0x0001, m_civRemotePort);
                        continue;
                    }
                    if (ptype == 0x06) {
                        m_civStream.remoteId = sentId;
                        sendOpenClose(true);
                        return true;
                    }
                }
            }

            if (data.size() > PING_SIZE && quint8(data[0x10]) == 0xC1) {
                return true;
            }
        }
    }

    if (error) {
        *error = "Timeout during CIV handshake.";
    }
    return false;
}

void IC705Client::sendControl(UdpStream &stream, quint16 pktType, bool tracked, quint16 seqUntracked, quint16 port) {
    QByteArray b = buildHeader(CONTROL_SIZE, pktType, stream.myId, stream.remoteId);
    if (!tracked) {
        putU16LE(b, 6, seqUntracked);
    } else {
        setExternalSeq(stream, b);
    }
    stream.socket->writeDatagram(b, m_radioAddr, port);
}

void IC705Client::sendLogin() {
    if (!m_ctrlStream.socket) {
        return;
    }
    m_tokRequest = quint16(QRandomGenerator::global()->bounded(65536));
    const QByteArray u = passcode(m_params.username);
    const QByteArray p = passcode(m_params.password);

    QByteArray b = buildHeader(LOGIN_SIZE, 0, m_ctrlStream.myId, m_ctrlStream.remoteId);
    putU32BE(b, 0x10, quint32(LOGIN_SIZE - 0x10));
    b[0x14] = char(0x01);
    b[0x15] = char(0x00);
    putU16BE(b, 0x16, m_authSeq);
    m_authSeq = quint16(m_authSeq + 1);
    putU16LE(b, 0x1A, m_tokRequest);

    b.replace(0x40, u.size(), u);
    b.replace(0x50, p.size(), p);

    QByteArray cn = m_params.compName.toLatin1();
    if (cn.size() > 16) {
        cn = cn.left(16);
    }
    b.replace(0x60, cn.size(), cn);

    setExternalSeq(m_ctrlStream, b);
    m_ctrlStream.socket->writeDatagram(b, m_radioAddr, CONTROL_PORT);
}

void IC705Client::sendToken(quint8 magic) {
    if (!m_ctrlStream.socket) {
        return;
    }
    QByteArray b = buildHeader(TOKEN_SIZE, 0, m_ctrlStream.myId, m_ctrlStream.remoteId);
    putU32BE(b, 0x10, quint32(TOKEN_SIZE - 0x10));
    b[0x14] = char(0x01);
    b[0x15] = char(magic);
    putU16BE(b, 0x16, m_authSeq);
    m_authSeq = quint16(m_authSeq + 1);
    putU16LE(b, 0x1A, m_tokRequest);
    putU32LE(b, 0x1C, m_token);
    putU16BE(b, 0x24, 0x0798);

    setExternalSeq(m_ctrlStream, b);
    m_ctrlStream.socket->writeDatagram(b, m_radioAddr, CONTROL_PORT);
}

void IC705Client::sendRequestStream() {
    if (!m_ctrlStream.socket) {
        return;
    }
    const QByteArray u = passcode(m_params.username);

    QByteArray b = buildHeader(CONNINFO_SIZE, 0, m_ctrlStream.myId, m_ctrlStream.remoteId);
    putU32BE(b, 0x10, quint32(CONNINFO_SIZE - 0x10));
    b[0x14] = char(0x01);
    b[0x15] = char(0x03);
    putU16BE(b, 0x16, m_authSeq);
    m_authSeq = quint16(m_authSeq + 1);
    putU16LE(b, 0x1A, m_tokRequest);
    putU32LE(b, 0x1C, m_token);

    if (!m_params.radioGuid.isEmpty()) {
        QByteArray guid = m_params.radioGuid.left(16);
        if (guid.size() < 16) {
            guid = guid.leftJustified(16, char(0x00));
        }
        b.replace(0x20, 16, guid);
    } else {
        putU16LE(b, 0x27, 0x8010);
        if (!m_params.radioMac.isEmpty()) {
            QByteArray mac = m_params.radioMac.left(6);
            if (mac.size() < 6) {
                mac = mac.leftJustified(6, char(0x00));
            }
            b.replace(0x2A, 6, mac);
        }
    }

    QByteArray dn = m_params.radioName.toLatin1();
    if (dn.size() > 32) {
        dn = dn.left(32);
    }
    b.replace(0x40, dn.size(), dn);

    b.replace(0x60, u.size(), u);
    b[0x70] = char(1);
    b[0x71] = char(0);
    b[0x72] = char(0x04);
    b[0x73] = char(0x00);
    putU32BE(b, 0x74, 48000);
    putU32BE(b, 0x78, 0);
    putU32BE(b, 0x7C, m_civLocalPort);
    putU32BE(b, 0x80, m_audioLocalPort);
    putU32BE(b, 0x84, 0);
    b[0x88] = char(1);

    setExternalSeq(m_ctrlStream, b);
    m_ctrlStream.socket->writeDatagram(b, m_radioAddr, CONTROL_PORT);
}

void IC705Client::sendOpenClose(bool open) {
    if (!m_civStream.socket) {
        return;
    }
    QByteArray b(OPENCLOSE_SIZE, char(0));
    putU32LE(b, 0, OPENCLOSE_SIZE);
    putU16LE(b, 4, 0);
    putU16LE(b, 6, 0);
    putU32LE(b, 8, m_civStream.myId);
    putU32LE(b, 12, m_civStream.remoteId);
    putU16LE(b, 0x10, 0x01C0);
    b[0x12] = char(0x00);
    putU16BE(b, 0x13, m_civSendSeqB);
    b[0x15] = open ? char(0x04) : char(0x00);
    m_civSendSeqB = quint16(m_civSendSeqB + 1);

    setExternalSeq(m_civStream, b);
    m_civStream.socket->writeDatagram(b, m_radioAddr, m_civRemotePort);
}

void IC705Client::handlePing(UdpStream &stream, const QByteArray &data, quint16 port) {
    quint32 size = 0;
    quint16 ptype = 0;
    quint16 pseq = 0;
    quint32 sentId = 0;
    quint32 remoteId = 0;
    if (!parseHeader(data, size, ptype, pseq, sentId, remoteId)) {
        return;
    }
    if (ptype != 0x07) {
        return;
    }
    if (data.size() != PING_SIZE) {
        return;
    }
    if (quint8(data[0x10]) != 0x00) {
        return;
    }
    QByteArray b(PING_SIZE, char(0));
    putU32LE(b, 0, PING_SIZE);
    putU16LE(b, 4, 0x07);
    putU16LE(b, 6, pseq);
    putU32LE(b, 8, stream.myId);
    putU32LE(b, 12, stream.remoteId);
    b[0x10] = char(0x01);
    b.replace(0x11, 4, data.mid(0x11, 4));
    stream.socket->writeDatagram(b, m_radioAddr, port);
}

void IC705Client::updateStatus(const QString &text) {
    if (m_statusText == text) {
        return;
    }
    m_statusText = text;
    emit statusTextChanged(text);
}

QByteArray IC705Client::passcode(const QString &text) {
    static const quint8 sequence[] = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0x47,0x5d,0x4c,0x42,0x66,0x20,0x23,0x46,0x4e,0x57,0x45,0x3d,0x67,0x76,0x60,0x41,
        0x62,0x39,0x59,0x2d,0x68,0x7e,0x7c,0x65,0x7d,0x49,0x29,0x72,0x73,0x78,0x21,0x6e,
        0x5a,0x5e,0x4a,0x3e,0x71,0x2c,0x2a,0x54,0x3c,0x3a,0x63,0x4f,0x43,0x75,0x27,0x79,
        0x5b,0x35,0x70,0x48,0x6b,0x56,0x6f,0x34,0x32,0x6c,0x30,0x61,0x6d,0x7b,0x2f,0x4b,
        0x64,0x38,0x2b,0x2e,0x50,0x40,0x3f,0x55,0x33,0x37,0x25,0x77,0x24,0x26,0x74,0x6a,
        0x28,0x53,0x4d,0x69,0x22,0x5c,0x44,0x31,0x36,0x58,0x3b,0x7a,0x51,0x5f,0x52,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    };
    QByteArray b = text.toLatin1();
    QByteArray out;
    const int maxLen = qMin(b.size(), 16);
    out.reserve(maxLen);
    for (int i = 0; i < maxLen; ++i) {
        int p = quint8(b[i]) + i;
        if (p > 126) {
            p = 32 + (p % 127);
        }
        out.append(char(sequence[p]));
    }
    return out;
}

quint32 IC705Client::computeMyId(const QHostAddress &localAddr, quint16 localPort) {
    const quint32 addr = localAddr.toIPv4Address();
    return (((addr >> 8) & 0xFF) << 24) | ((addr & 0xFF) << 16) | (localPort & 0xFFFF);
}

bool IC705Client::parseHeader(const QByteArray &data, quint32 &size, quint16 &ptype, quint16 &pseq,
                              quint32 &sentId, quint32 &remoteId) {
    if (data.size() < CONTROL_SIZE) {
        return false;
    }
    size = getU32LE(data, 0);
    ptype = getU16LE(data, 4);
    pseq = getU16LE(data, 6);
    sentId = getU32LE(data, 8);
    remoteId = getU32LE(data, 12);
    return true;
}

QHostAddress IC705Client::pickLocalAddress(const QHostAddress &remoteAddr, quint16 remotePort) {
    QUdpSocket tmp;
    tmp.connectToHost(remoteAddr, remotePort);
    return tmp.localAddress();
}

bool IC705Client::reserveTwoUdpPorts(const QHostAddress &localAddr, quint16 &port1, quint16 &port2) {
    for (int attempt = 0; attempt < 5; ++attempt) {
        QUdpSocket s1;
        if (!s1.bind(localAddr, 0)) {
            continue;
        }
        const quint16 p1 = s1.localPort();
        QUdpSocket s2;
        if (!s2.bind(localAddr, 0)) {
            continue;
        }
        const quint16 p2 = s2.localPort();
        if (p1 == p2) {
            continue;
        }
        port1 = p1;
        port2 = p2;
        return true;
    }
    return false;
}

void IC705Client::putU16LE(QByteArray &buf, int offset, quint16 value) {
    const quint16 v = qToLittleEndian(value);
    memcpy(buf.data() + offset, &v, sizeof(v));
}

void IC705Client::putU32LE(QByteArray &buf, int offset, quint32 value) {
    const quint32 v = qToLittleEndian(value);
    memcpy(buf.data() + offset, &v, sizeof(v));
}

void IC705Client::putU16BE(QByteArray &buf, int offset, quint16 value) {
    const quint16 v = qToBigEndian(value);
    memcpy(buf.data() + offset, &v, sizeof(v));
}

void IC705Client::putU32BE(QByteArray &buf, int offset, quint32 value) {
    const quint32 v = qToBigEndian(value);
    memcpy(buf.data() + offset, &v, sizeof(v));
}

quint16 IC705Client::getU16LE(const QByteArray &buf, int offset) {
    return qFromLittleEndian<quint16>(reinterpret_cast<const uchar *>(buf.constData() + offset));
}

quint32 IC705Client::getU32LE(const QByteArray &buf, int offset) {
    return qFromLittleEndian<quint32>(reinterpret_cast<const uchar *>(buf.constData() + offset));
}

quint16 IC705Client::getU16BE(const QByteArray &buf, int offset) {
    return qFromBigEndian<quint16>(reinterpret_cast<const uchar *>(buf.constData() + offset));
}

QByteArray IC705Client::buildHeader(quint32 totalLen, quint16 pktType, quint32 myId, quint32 remoteId) {
    if (totalLen < CONTROL_SIZE) {
        totalLen = CONTROL_SIZE;
    }
    QByteArray b(int(totalLen), char(0));
    putU32LE(b, 0, totalLen);
    putU16LE(b, 4, pktType);
    putU16LE(b, 6, 0);
    putU32LE(b, 8, myId);
    putU32LE(b, 12, remoteId);
    return b;
}

void IC705Client::setExternalSeq(UdpStream &stream, QByteArray &buf) {
    if (buf.size() < 8) {
        return;
    }
    buf[6] = char(stream.sendSeq & 0xFF);
    buf[7] = char((stream.sendSeq >> 8) & 0xFF);
    stream.sendSeq = quint16(stream.sendSeq + 1);
}
