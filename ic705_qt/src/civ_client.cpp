#include "civ_client.h"

#include <QDateTime>
#include <QtGlobal>

namespace {
constexpr quint8 kCivPreamble = 0xFE;
constexpr quint8 kCivEnd = 0xFD;
constexpr quint8 kAddrRadio = 0xA4;
constexpr quint8 kAddrPc = 0xE0;
constexpr int kSpectrumWidth = 475;
constexpr int kSpectrumDataStart = 19;
constexpr float kRefLevelDefault = -77.0f;
constexpr float kRawMax = 160.0f;
constexpr float kScaleDbPerPoint = 0.5f;

}

CivClient::CivClient(QObject *parent)
    : QObject(parent),
      m_connected(false),
      m_statusText("Disconnected"),
      m_freqMHz(0.0),
      m_refLevel(0) {
    m_socket.setSocketOption(QAbstractSocket::LowDelayOption, 1);

    connect(&m_socket, &QTcpSocket::connected, this, &CivClient::onConnected);
    connect(&m_socket, &QTcpSocket::disconnected, this, &CivClient::onDisconnected);
    connect(&m_socket, &QTcpSocket::readyRead, this, &CivClient::onReadyRead);
    connect(&m_socket, &QTcpSocket::errorOccurred, this, &CivClient::onErrorOccurred);

    m_pollTimer.setInterval(2000);
    m_pollTimer.setTimerType(Qt::CoarseTimer);
    connect(&m_pollTimer, &QTimer::timeout, this, &CivClient::onPollTimeout);
}

bool CivClient::connected() const {
    return m_connected;
}

QString CivClient::statusText() const {
    return m_statusText;
}

double CivClient::freqMHz() const {
    return m_freqMHz;
}

int CivClient::refLevel() const {
    return m_refLevel;
}

void CivClient::connectToDefault() {
    if (m_connected) {
        return;
    }
    updateStatus("Connecting 127.0.0.1:50002...");
    m_socket.connectToHost(QStringLiteral("127.0.0.1"), 50002);
}

void CivClient::disconnectFromHost() {
    if (!m_connected && m_socket.state() == QAbstractSocket::UnconnectedState) {
        return;
    }
    m_pollTimer.stop();
    if (m_socket.state() == QAbstractSocket::ConnectedState) {
        m_socket.write(buildCivFrame(0x27, 0x10, QByteArray(1, char(0x00))));
    }
    m_socket.disconnectFromHost();
}

void CivClient::onConnected() {
    m_connected = true;
    emit connectedChanged();
    updateStatus("Connected");

    m_socket.write(buildCivFrame(0x27, 0x10, QByteArray(1, char(0x01))));
    m_socket.write(buildCivFrame(0x03));
    m_socket.write(buildCivFrame(0x27, 0x19));
    m_pollTimer.start();
}

void CivClient::onDisconnected() {
    m_connected = false;
    emit connectedChanged();
    updateStatus("Disconnected");
    m_pollTimer.stop();
}

void CivClient::onReadyRead() {
    m_buffer.append(m_socket.readAll());
    auto messages = extractMessages(m_buffer);
    for (const auto &msg : messages) {
        processMessage(msg);
    }
}

void CivClient::onErrorOccurred(QAbstractSocket::SocketError) {
    updateStatus(QStringLiteral("Socket error: %1").arg(m_socket.errorString()));
}

void CivClient::onPollTimeout() {
    if (m_socket.state() != QAbstractSocket::ConnectedState) {
        return;
    }
    m_socket.write(buildCivFrame(0x03));
    m_socket.write(buildCivFrame(0x27, 0x19));
}

void CivClient::updateStatus(const QString &text) {
    if (m_statusText == text) {
        return;
    }
    m_statusText = text;
    emit statusTextChanged();
}

void CivClient::processMessage(const QByteArray &msg) {
    if (msg.size() < 5) {
        return;
    }

    const quint8 cmd = quint8(msg[4]);
    if (cmd == 0x03 && msg.size() >= 11) {
        const double freq = decodeFrequencyBcd(msg.mid(5, 5));
        if (freq > 0.0 && !qFuzzyCompare(freq, m_freqMHz)) {
            m_freqMHz = freq;
            emit freqChanged();
        }
        return;
    }

    if (cmd == 0x27 && msg.size() >= 8) {
        const quint8 subCmd = quint8(msg[5]);
        if (subCmd == 0x19) {
            const int ref = decodeRefLevel(msg);
            if (ref != m_refLevel) {
                m_refLevel = ref;
                emit refLevelChanged();
            }
            return;
        }
        if (msg.size() > kSpectrumDataStart + 2) {
            const int end = msg.size() - 1;
            if (end <= kSpectrumDataStart) {
                return;
            }
            const int count = end - kSpectrumDataStart;
            QVector<float> raw(count);
            for (int i = 0; i < count; ++i) {
                raw[i] = float(quint8(msg[kSpectrumDataStart + i]));
            }

            QVector<float> dbm(count);
            for (int i = 0; i < count; ++i) {
                dbm[i] = kRefLevelDefault - (kRawMax - raw[i]) * kScaleDbPerPoint;
            }

            QVector<float> resized = resample(dbm, kSpectrumWidth);
            emit spectrumReady(resized);
        }
    }
}

QList<QByteArray> CivClient::extractMessages(QByteArray &buffer) {
    QList<QByteArray> messages;
    while (true) {
        int start = buffer.indexOf(char(kCivPreamble));
        if (start < 0) {
            buffer.clear();
            break;
        }
        if (start + 1 >= buffer.size()) {
            if (start > 0) {
                buffer.remove(0, start);
            }
            break;
        }
        if (quint8(buffer[start + 1]) != kCivPreamble) {
            buffer.remove(0, start + 1);
            continue;
        }
        if (start > 0) {
            buffer.remove(0, start);
        }
        int end = buffer.indexOf(char(kCivEnd));
        if (end < 0) {
            break;
        }
        const QByteArray msg = buffer.left(end + 1);
        messages.append(msg);
        buffer.remove(0, end + 1);
    }
    return messages;
}

double CivClient::decodeFrequencyBcd(const QByteArray &data) {
    if (data.size() < 5) {
        return 0.0;
    }
    const int factors[5] = {1, 100, 10000, 1000000, 100000000};
    quint64 freqHz = 0;
    for (int i = 0; i < 5; ++i) {
        const quint8 byte = quint8(data[i]);
        const quint8 low = byte & 0x0F;
        const quint8 high = (byte >> 4) & 0x0F;
        freqHz += quint64(low) * factors[i];
        freqHz += quint64(high) * factors[i] * 10;
    }
    return double(freqHz) / 1'000'000.0;
}

int CivClient::decodeRefLevel(const QByteArray &msg) {
    if (msg.size() < 9) {
        return 0;
    }
    const quint8 low = quint8(msg[6]);
    const quint8 high = quint8(msg[7]);
    int value = int(low & 0x0F) + int((low >> 4) & 0x0F) * 10;
    if (high & 0x01) {
        value = -value;
    }
    return value;
}

QVector<float> CivClient::resample(const QVector<float> &input, int targetSize) {
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

QByteArray CivClient::buildCivFrame(quint8 cmd, quint8 subCmd, const QByteArray &payload) {
    QByteArray frame;
    frame.append(char(kCivPreamble));
    frame.append(char(kCivPreamble));
    frame.append(char(kAddrRadio));
    frame.append(char(kAddrPc));
    frame.append(char(cmd));
    if (subCmd != 0x00) {
        frame.append(char(subCmd));
    }
    if (!payload.isEmpty()) {
        frame.append(payload);
    }
    frame.append(char(kCivEnd));
    return frame;
}
