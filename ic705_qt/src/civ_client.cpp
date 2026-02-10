#include "civ_client.h"

#include <QtGlobal>
#include <QTimer>
#include <QDebug>

namespace {
constexpr int kSpectrumWidth = 475;
constexpr int kSpectrumDataStart = 19;
constexpr float kRefLevelDefault = -77.0f;
constexpr float kRawMax = 160.0f;
constexpr float kScaleDbPerPoint = 0.5f;
constexpr quint8 kCivRadioAddr = 0xA4;
constexpr quint8 kCivPcAddr = 0xE0;
constexpr const char *kRadioIp = "192.168.59.1";
constexpr const char *kRadioUser = "IC-705-7";
constexpr const char *kRadioPass = "bouter20xx";
constexpr const char *kRadioName = "IC-705-7";
constexpr const char *kRadioMac = "0090C713CA75";

QByteArray encodeFrequencyBcd(double valueMHz, bool *ok) {
    if (ok) {
        *ok = false;
    }
    if (!(valueMHz > 0.0)) {
        return QByteArray();
    }
    const quint64 hz = quint64(valueMHz * 1'000'000.0 + 0.5);
    if (hz == 0 || hz > 9'999'999'999ULL) {
        return QByteArray();
    }

    quint64 tmp = hz;
    QByteArray out;
    out.resize(5);
    for (int i = 0; i < 5; ++i) {
        const quint8 low = quint8(tmp % 10);
        tmp /= 10;
        const quint8 high = quint8(tmp % 10);
        tmp /= 10;
        out[i] = char((high << 4) | low);
    }

    if (ok) {
        *ok = true;
    }
    return out;
}

QByteArray encodeSpanBcd3Hz(quint64 spanHz, bool *ok) {
    if (ok) {
        *ok = false;
    }
    if (spanHz == 0 || spanHz > 999999ULL) {
        return QByteArray();
    }

    const quint8 d100k = quint8((spanHz / 100000ULL) % 10ULL);
    const quint8 d10k = quint8((spanHz / 10000ULL) % 10ULL);
    const quint8 d1k = quint8((spanHz / 1000ULL) % 10ULL);
    const quint8 d100 = quint8((spanHz / 100ULL) % 10ULL);
    const quint8 d10 = quint8((spanHz / 10ULL) % 10ULL);
    const quint8 d1 = quint8(spanHz % 10ULL);

    QByteArray out;
    out.resize(3);
    out[0] = char((d100k << 4) | d10k);
    out[1] = char((d1k << 4) | d100);
    out[2] = char((d10 << 4) | d1);

    if (ok) {
        *ok = true;
    }
    return out;
}

double decodeSpanBcd3ToHz(const QByteArray &data) {
    if (data.size() < 3) {
        return 0.0;
    }
    const quint8 b0 = quint8(data[0]);
    const quint8 b1 = quint8(data[1]);
    const quint8 b2 = quint8(data[2]);

    const quint8 d100k = (b0 >> 4) & 0x0F;
    const quint8 d10k = b0 & 0x0F;
    const quint8 d1k = (b1 >> 4) & 0x0F;
    const quint8 d100 = b1 & 0x0F;
    const quint8 d10 = (b2 >> 4) & 0x0F;
    const quint8 d1 = b2 & 0x0F;

    const quint64 hz = quint64(d100k) * 100000ULL +
                       quint64(d10k) * 10000ULL +
                       quint64(d1k) * 1000ULL +
                       quint64(d100) * 100ULL +
                       quint64(d10) * 10ULL +
                       quint64(d1);
    return double(hz);
}

double decodeBcdToHz(const QByteArray &data) {
    static const quint64 factors[5] = {
        1ULL,
        100ULL,
        10000ULL,
        1000000ULL,
        100000000ULL
    };
    const int n = qMin(data.size(), 5);
    quint64 hz = 0;
    for (int i = 0; i < n; ++i) {
        const quint8 byte = quint8(data[i]);
        const quint8 low = byte & 0x0F;
        const quint8 high = (byte >> 4) & 0x0F;
        hz += quint64(low) * factors[i];
        hz += quint64(high) * factors[i] * 10ULL;
    }
    return double(hz);
}

quint16 scopeSpanCodeFromKHz(double spanKHz) {
    // IC-705 scope span code mapping (27 15 .... XX XX ....)
    // 2.5 kHz is encoded as 0x0002, not 0x0003.
    if (qAbs(spanKHz - 2.5) < 0.11) {
        return 2;
    }
    if (qAbs(spanKHz - 5.0) < 0.11) {
        return 5;
    }
    if (qAbs(spanKHz - 10.0) < 0.11) {
        return 10;
    }
    if (qAbs(spanKHz - 25.0) < 0.11) {
        return 25;
    }
    if (qAbs(spanKHz - 50.0) < 0.11) {
        return 50;
    }
    if (qAbs(spanKHz - 100.0) < 0.11) {
        return 100;
    }
    if (qAbs(spanKHz - 250.0) < 0.11) {
        return 250;
    }
    if (qAbs(spanKHz - 500.0) < 0.11) {
        return 500;
    }
    return 0;
}

double scopeSpanKHzFromCode(quint16 code) {
    if (code == 2) {
        return 2.5;
    }
    switch (code) {
    case 5:
    case 10:
    case 25:
    case 50:
    case 100:
    case 250:
    case 500:
        return double(code);
    default:
        return 0.0;
    }
}

QByteArray buildScopeSpanPayloadCode(quint16 spanCode) {
    QByteArray payload;
    payload.reserve(7);
    payload.append(char(0x15));
    payload.append(char(0x00));
    payload.append(char(0x00));
    payload.append(char(spanCode & 0xFF));
    payload.append(char((spanCode >> 8) & 0xFF));
    payload.append(char(0x00));
    payload.append(char(0x00));
    return payload;
}

bool buildScopeSpanPayloadAlt(double spanKHz, QByteArray *payloadOut) {
    if (!payloadOut) {
        return false;
    }
    quint8 b2 = 0x00;
    quint8 b3 = 0x00;
    if (qAbs(spanKHz - 2.5) < 0.11) {
        b2 = 0x25; b3 = 0x00;
    } else if (qAbs(spanKHz - 5.0) < 0.11) {
        b2 = 0x50; b3 = 0x00;
    } else if (qAbs(spanKHz - 10.0) < 0.11) {
        b2 = 0x00; b3 = 0x01;
    } else if (qAbs(spanKHz - 25.0) < 0.11) {
        b2 = 0x50; b3 = 0x02;
    } else if (qAbs(spanKHz - 50.0) < 0.11) {
        b2 = 0x00; b3 = 0x05;
    } else if (qAbs(spanKHz - 100.0) < 0.11) {
        b2 = 0x00; b3 = 0x10;
    } else if (qAbs(spanKHz - 250.0) < 0.11) {
        b2 = 0x00; b3 = 0x25;
    } else if (qAbs(spanKHz - 500.0) < 0.11) {
        b2 = 0x00; b3 = 0x50;
    } else {
        return false;
    }

    QByteArray payload;
    payload.reserve(7);
    payload.append(char(0x15));
    payload.append(char(0x00));
    payload.append(char(0x00));
    payload.append(char(b2));
    payload.append(char(b3));
    payload.append(char(0x00));
    payload.append(char(0x00));
    *payloadOut = payload;
    return true;
}

double decodeScopeSpanAltPayloadKHz(const QByteArray &payload) {
    if (payload.size() < 6) {
        return 0.0;
    }
    const quint8 b2 = quint8(payload[2]);
    const quint8 b3 = quint8(payload[3]);
    if (b2 == 0x25 && b3 == 0x00) return 2.5;
    if (b2 == 0x50 && b3 == 0x00) return 5.0;
    if (b2 == 0x00 && b3 == 0x01) return 10.0;
    if (b2 == 0x50 && b3 == 0x02) return 25.0;
    if (b2 == 0x00 && b3 == 0x05) return 50.0;
    if (b2 == 0x00 && b3 == 0x10) return 100.0;
    if (b2 == 0x00 && b3 == 0x25) return 250.0;
    if (b2 == 0x00 && b3 == 0x50) return 500.0;
    return 0.0;
}

}

CivClient::CivClient(QObject *parent)
    : QObject(parent),
      m_connected(false),
      m_statusText("Disconnected"),
      m_freqMHz(0.0),
      m_spanKHz(5.0),
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

double CivClient::spanKHz() const {
    return m_spanKHz;
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

bool CivClient::setFrequencyMHz(double valueMHz) {
    if (!m_connected) {
        updateStatus(QStringLiteral("Not connected"));
        return false;
    }
    bool ok = false;
    const QByteArray bcd = encodeFrequencyBcd(valueMHz, &ok);
    if (!ok) {
        updateStatus(QStringLiteral("Invalid frequency"));
        return false;
    }

    updateStatus(QStringLiteral("Set freq request: %1 MHz").arg(valueMHz, 0, 'f', 6));
    m_client.sendCivCmd(0x05, bcd);
    // Query shortly after write so UI reflects the rig's actual value.
    QTimer::singleShot(120, this, [this]() {
        if (m_connected) {
            m_client.sendCivCmd(0x03);
        }
    });
    return true;
}

bool CivClient::setScopeSpanKHz(double valueKHz) {
    if (!m_connected) {
        updateStatus(QStringLiteral("Not connected"));
        return false;
    }
    if (!(valueKHz > 0.0)) {
        updateStatus(QStringLiteral("Invalid span"));
        return false;
    }
    QByteArray payload;
    if (!buildScopeSpanPayloadAlt(valueKHz, &payload)) {
        updateStatus(QStringLiteral("Invalid span"));
        return false;
    }

    updateStatus(QStringLiteral("Set span request: %1 kHz").arg(valueKHz, 0, 'f', 1));

    // 27 15 is valid only in Center / Scroll-C scope modes.
    // Force Center mode first: 27 14 00 00.
    QByteArray modePayload;
    modePayload.append(char(0x14));
    modePayload.append(char(0x00));
    modePayload.append(char(0x00));
    qInfo().noquote() << "SPAN TX 27 14 payload = 00 00";
    m_client.sendCivCmd(0x27, modePayload);

    // Send span write shortly after mode switch.
    QTimer::singleShot(60, this, [this, payload]() {
        if (!m_connected) {
            return;
        }
        qInfo().noquote() << "SPAN TX 27 15 payload (ALT) =" << payload.mid(1).toHex(' ');
        m_client.sendCivCmd(0x27, payload);
    });

    // Poll span shortly after write.
    QTimer::singleShot(180, this, [this]() {
        if (m_connected) {
            QByteArray req;
            req.append(char(0x15));
            m_client.sendCivCmd(0x27, req);
        }
    });
    return true;
}

void CivClient::onPollTimeout() {
    if (!m_connected) {
        return;
    }
    qInfo().noquote() << "POLL TX 03 / 27 15 / 27 19";
    m_client.sendCivCmd(0x03);
    m_client.sendCivCmd(0x27, QByteArray(1, char(0x15)));
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

    const quint8 to = quint8(msg[2]);
    const quint8 from = quint8(msg[3]);
    const bool isEcho = (to == kCivRadioAddr && from == kCivPcAddr);
    const bool isFromRadio = (to == kCivPcAddr && from == kCivRadioAddr);

    const quint8 cmd = quint8(msg[4]);
    if (cmd == 0xFB) {
        updateStatus(QStringLiteral("CI-V ACK"));
        return;
    }
    if (cmd == 0xFA) {
        updateStatus(QStringLiteral("CI-V REJECT"));
        return;
    }

    if (cmd == 0x03 && msg.size() >= 11 && isFromRadio) {
        const double freq = decodeFrequencyBcd(msg.mid(5, 5));
        if (freq > 0.0 && !qFuzzyCompare(freq, m_freqMHz)) {
            m_freqMHz = freq;
            emit freqChanged();
        }
        return;
    }

    if (cmd == 0x27 && msg.size() >= 8) {
        const quint8 subCmd = quint8(msg[5]);
        if (subCmd == 0x15) {
            qInfo().noquote() << "SPAN RX 27 15 frame =" << msg.toHex(' ') << "size =" << msg.size()
                              << "to=" << QString::number(to, 16)
                              << "from=" << QString::number(from, 16)
                              << (isEcho ? "(echo)" : (isFromRadio ? "(radio)" : "(other)"));
            if (!isFromRadio) {
                return;
            }
            // Payload variants exist; prefer the explicit 00 00 XX XX 00 00 layout.
            const int payloadLen = msg.size() - 7;  // remove FE FE to from cmd sub ... FD
            if (payloadLen <= 0) {
                qWarning() << "SPAN RX 27 15 without payload";
                return;
            }
            const QByteArray payload = msg.mid(6, payloadLen);
            qInfo().noquote() << "SPAN RX 27 15 raw payload =" << payload.toHex(' ');
            double spanKHz = 0.0;
            spanKHz = decodeScopeSpanAltPayloadKHz(payload);
            if (payload.size() >= 6) {
                const quint8 lo = quint8(payload[2]);
                const quint8 hi = quint8(payload[3]);
                const quint16 spanCode = quint16((quint16(hi) << 8) | quint16(lo));
                if (spanKHz <= 0.0) {
                    spanKHz = scopeSpanKHzFromCode(spanCode);
                }
            }
            if (spanKHz <= 0.0 && payload.size() >= 3) {
                const double spanHz = decodeSpanBcd3ToHz(payload.right(3));
                if (spanHz > 0.0) {
                    spanKHz = spanHz / 1000.0;
                }
            }
            if (spanKHz <= 0.0) {
                // Fallback for nonstandard framing variants.
                const double spanHz = decodeBcdToHz(payload);
                if (spanHz > 0.0) {
                    spanKHz = spanHz / 1000.0;
                }
            }
            if (spanKHz > 0.0 && !qFuzzyCompare(spanKHz, m_spanKHz)) {
                m_spanKHz = spanKHz;
                qInfo().noquote() << "SPAN RX 27 15 payload =" << payload.toHex(' ')
                                  << "decoded =" << QString::number(spanKHz, 'f', 3) << "kHz";
                emit spanChanged();
            }
            return;
        }
        if (subCmd == 0x19 && isFromRadio) {
            const int ref = decodeRefLevel(msg);
            if (ref != m_refLevel) {
                m_refLevel = ref;
                emit refLevelChanged();
            }
            return;
        }
        if (msg.size() > kSpectrumDataStart + 2 && isFromRadio) {
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
