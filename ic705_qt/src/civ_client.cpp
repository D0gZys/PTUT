#include "civ_client.h"

#include <QtGlobal>

namespace {
constexpr int kSpectrumWidth = 475;
constexpr int kSpectrumDataStart = 19;
constexpr float kRefLevelDefault = -77.0f;
constexpr float kRawMax = 160.0f;
constexpr float kScaleDbPerPoint = 0.5f;
constexpr const char *kRadioIp = "192.168.59.1";
constexpr const char *kRadioUser = "IC-705-7";
constexpr const char *kRadioPass = "bouter20xx";
constexpr const char *kRadioName = "IC-705-7";
constexpr const char *kRadioMac = "0090C713CA75";

}

CivClient::CivClient(QObject *parent)
    : QObject(parent),
      m_connected(false),
      m_statusText("Disconnected"),
      m_freqMHz(0.0),
      m_refLevel(0) {
    connect(&m_client, &IC705Client::civFrameReceived, this,
            [this](const QByteArray &payload) { processMessage(payload); });
    connect(&m_client, &IC705Client::connectedChanged, this, [this](bool connected) {
        if (m_connected == connected) {
            return;
        }
        m_connected = connected;
        emit connectedChanged();
        if (!connected) {
            m_pollTimer.stop();
            updateStatus("Disconnected");
        }
    });
    connect(&m_client, &IC705Client::statusTextChanged, this, &CivClient::updateStatus);

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
    connectWithParams(QString::fromLatin1(kRadioIp),
                      QString::fromLatin1(kRadioUser),
                      QString::fromLatin1(kRadioPass),
                      QString::fromLatin1(kRadioName),
                      QString::fromLatin1(kRadioMac));
}

void CivClient::connectWithParams(const QString &ip,
                                  const QString &username,
                                  const QString &password,
                                  const QString &radioName,
                                  const QString &radioMac) {
    if (m_connected) {
        return;
    }
    IC705Client::Params params;
    params.radioIp = ip.trimmed();
    params.username = username.trimmed();
    params.password = password;
    params.radioName = radioName.trimmed().isEmpty() ? QStringLiteral("IC-705") : radioName.trimmed();
    bool ok = false;
    params.radioMac = parseMacBytes(radioMac, &ok);
    if (!ok) {
        updateStatus(QStringLiteral("Invalid MAC address."));
        return;
    }

    if (params.radioIp.isEmpty()) {
        updateStatus(QStringLiteral("Radio IP missing."));
        return;
    }
    if (params.username.isEmpty() || params.password.isEmpty()) {
        updateStatus(QStringLiteral("Username/password missing."));
        return;
    }

    updateStatus(QStringLiteral("Connecting %1...").arg(params.radioIp));
    QString error;
    if (!m_client.connectToRadio(params, 20000, &error)) {
        updateStatus(error.isEmpty() ? QStringLiteral("Connection failed") : error);
        return;
    }

    QByteArray scopeOn;
    scopeOn.append(char(0x10));
    scopeOn.append(char(0x01));
    m_client.sendCivCmd(0x27, scopeOn);
    QByteArray scopeDataOn;
    scopeDataOn.append(char(0x11));
    scopeDataOn.append(char(0x01));
    m_client.sendCivCmd(0x27, scopeDataOn);
    m_client.sendCivCmd(0x03);
    m_client.sendCivCmd(0x27, QByteArray(1, char(0x19)));

    m_pollTimer.start();
}

void CivClient::disconnectFromHost() {
    m_pollTimer.stop();
    if (m_connected) {
        QByteArray scopeDataOff;
        scopeDataOff.append(char(0x11));
        scopeDataOff.append(char(0x00));
        m_client.sendCivCmd(0x27, scopeDataOff);

        QByteArray scopeOff;
        scopeOff.append(char(0x10));
        scopeOff.append(char(0x00));
        m_client.sendCivCmd(0x27, scopeOff);
    }
    m_client.close();
}

void CivClient::onPollTimeout() {
    if (!m_connected) {
        return;
    }
    m_client.sendCivCmd(0x03);
    m_client.sendCivCmd(0x27, QByteArray(1, char(0x19)));
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
            const QByteArray data = msg.mid(5, msg.size() - 6);
            const int base = (!data.isEmpty() && quint8(data[0]) == 0x00) ? 1 : 0;
            const int headerLen = base + 15;
            int rawOffset = -1;
            int count = 0;
            if (data.size() >= headerLen + kSpectrumWidth) {
                rawOffset = headerLen;
                count = kSpectrumWidth;
            } else if (data.size() > (kSpectrumDataStart - 5)) {
                rawOffset = kSpectrumDataStart - 5;
                count = data.size() - rawOffset;
            }
            if (rawOffset < 0 || count <= 0) {
                return;
            }
            QVector<float> raw(count);
            for (int i = 0; i < count; ++i) {
                raw[i] = float(quint8(data[rawOffset + i]));
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

QByteArray CivClient::parseMacBytes(const QString &text, bool *ok) {
    QString cleaned = text;
    cleaned.remove(':');
    cleaned.remove('-');
    cleaned.remove(' ');
    if (cleaned.isEmpty()) {
        if (ok) {
            *ok = true;
        }
        return QByteArray();
    }
    if (cleaned.size() != 12) {
        if (ok) {
            *ok = false;
        }
        return QByteArray();
    }
    QByteArray out;
    out.resize(6);
    for (int i = 0; i < 6; ++i) {
        bool localOk = false;
        const int value = cleaned.mid(i * 2, 2).toInt(&localOk, 16);
        if (!localOk) {
            if (ok) {
                *ok = false;
            }
            return QByteArray();
        }
        out[i] = char(value & 0xFF);
    }
    if (ok) {
        *ok = true;
    }
    return out;
}
