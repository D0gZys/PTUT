#include "waterfall_model.h"

#include <QtGlobal>
#include <cstring>

namespace {
constexpr int kWaterfallWidth = 475;
constexpr int kWaterfallHeight = 200;

constexpr QRgb kColors[] = {
    qRgb(0, 0, 0),
    qRgb(0, 0, 128),
    qRgb(0, 255, 255),
    qRgb(0, 255, 0),
    qRgb(255, 255, 0),
    qRgb(255, 128, 0),
    qRgb(255, 0, 0),
    qRgb(255, 255, 255)
};

QRgb lerpColor(QRgb a, QRgb b, float t) {
    const int r = qRed(a) + static_cast<int>((qRed(b) - qRed(a)) * t);
    const int g = qGreen(a) + static_cast<int>((qGreen(b) - qGreen(a)) * t);
    const int bch = qBlue(a) + static_cast<int>((qBlue(b) - qBlue(a)) * t);
    return qRgb(r, g, bch);
}

QVector<float> resampleLine(const QVector<float> &input, int targetSize) {
    if (input.isEmpty() || targetSize <= 0) {
        return QVector<float>();
    }
    if (input.size() == targetSize) {
        return input;
    }
    QVector<float> out(targetSize, 0.0f);
    const int inSize = input.size();
    for (int i = 0; i < targetSize; ++i) {
        const float pos = (inSize - 1) * (static_cast<float>(i) / (targetSize - 1));
        const int idx = static_cast<int>(pos);
        const int idx2 = qMin(idx + 1, inSize - 1);
        const float t = pos - idx;
        out[i] = input[idx] * (1.0f - t) + input[idx2] * t;
    }
    return out;
}
}

WaterfallModel::WaterfallModel(QObject *parent)
    : QObject(parent),
      m_image(kWaterfallWidth, kWaterfallHeight, QImage::Format_ARGB32),
      m_width(kWaterfallWidth),
      m_height(kWaterfallHeight),
      m_dbmMin(-160.0f),
      m_dbmMax(-80.0f),
      m_values(kWaterfallWidth * kWaterfallHeight, -160.0f) {
    m_image.fill(qRgb(0, 0, 0));
}

const QImage &WaterfallModel::image() const {
    return m_image;
}

int WaterfallModel::width() const {
    return m_width;
}

int WaterfallModel::height() const {
    return m_height;
}

float WaterfallModel::dbmMin() const {
    return m_dbmMin;
}

float WaterfallModel::dbmMax() const {
    return m_dbmMax;
}

void WaterfallModel::setDbmMin(float value) {
    setDbmRange(value, m_dbmMax);
}

void WaterfallModel::setDbmMax(float value) {
    setDbmRange(m_dbmMin, value);
}

void WaterfallModel::setDbmRange(float minValue, float maxValue) {
    float min = minValue;
    float max = maxValue;
    if (max - min < 1.0f) {
        max = min + 1.0f;
    }
    if (qFuzzyCompare(min, m_dbmMin) && qFuzzyCompare(max, m_dbmMax)) {
        return;
    }
    m_dbmMin = min;
    m_dbmMax = max;
    rebuildImage();
    emit rangeChanged();
}

void WaterfallModel::clear() {
    m_image.fill(qRgb(0, 0, 0));
    m_values.fill(m_dbmMin);
    emit imageChanged();
}

void WaterfallModel::setHeight(int height) {
    const int newHeight = qMax(1, height);
    if (newHeight == m_height) {
        return;
    }

    QVector<float> newValues(m_width * newHeight, m_dbmMin);
    const int copyHeight = qMin(m_height, newHeight);
    if (!m_values.isEmpty()) {
        for (int y = 0; y < copyHeight; ++y) {
            std::memcpy(newValues.data() + y * m_width,
                        m_values.constData() + y * m_width,
                        sizeof(float) * m_width);
        }
    }

    m_height = newHeight;
    m_values.swap(newValues);
    m_image = QImage(m_width, m_height, QImage::Format_ARGB32);
    rebuildImage();
    emit sizeChanged();
}

float WaterfallModel::valueAt(int x, int y) const {
    if (m_values.isEmpty()) {
        return m_dbmMin;
    }
    const int clampedX = qBound(0, x, m_width - 1);
    const int clampedY = qBound(0, y, m_height - 1);
    const int idx = clampedY * m_width + clampedX;
    if (idx < 0 || idx >= m_values.size()) {
        return m_dbmMin;
    }
    return m_values[idx];
}

void WaterfallModel::pushLine(const QVector<float> &samples) {
    if (samples.isEmpty() || m_image.isNull()) {
        return;
    }

    QVector<float> line = resampleLine(samples, m_width);

    const int rowBytes = m_image.bytesPerLine();
    uchar *bits = m_image.bits();
    std::memmove(bits + rowBytes, bits, rowBytes * (m_height - 1));

    QRgb *row = reinterpret_cast<QRgb *>(bits);
    const float range = (m_dbmMax - m_dbmMin) > 0.001f ? (m_dbmMax - m_dbmMin) : 1.0f;

    if (!m_values.isEmpty()) {
        std::memmove(m_values.data() + m_width, m_values.data(),
                     sizeof(float) * m_width * (m_height - 1));
    }

    for (int x = 0; x < m_width; ++x) {
        float t = (line[x] - m_dbmMin) / range;
        row[x] = mapColor(t);
        if (!m_values.isEmpty()) {
            m_values[x] = line[x];
        }
    }

    emit imageChanged();
}

QRgb WaterfallModel::mapColor(float value) const {
    float t = value;
    if (t < 0.0f) {
        t = 0.0f;
    } else if (t > 1.0f) {
        t = 1.0f;
    }

    const int count = static_cast<int>(sizeof(kColors) / sizeof(kColors[0]));
    if (count <= 1) {
        return (count == 1) ? kColors[0] : qRgb(0, 0, 0);
    }

    const float scaled = t * float(count - 1);
    const int idx = qBound(0, int(scaled), count - 2);
    const float local = scaled - float(idx);
    return lerpColor(kColors[idx], kColors[idx + 1], local);
}

void WaterfallModel::rebuildImage() {
    if (m_image.isNull() || m_values.isEmpty()) {
        m_image.fill(qRgb(0, 0, 0));
        emit imageChanged();
        return;
    }

    const float range = (m_dbmMax - m_dbmMin) > 0.001f ? (m_dbmMax - m_dbmMin) : 1.0f;
    for (int y = 0; y < m_height; ++y) {
        QRgb *row = reinterpret_cast<QRgb *>(m_image.scanLine(y));
        const int base = y * m_width;
        for (int x = 0; x < m_width; ++x) {
            float t = (m_values[base + x] - m_dbmMin) / range;
            row[x] = mapColor(t);
        }
    }
    emit imageChanged();
}
