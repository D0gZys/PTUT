#include "spectrum_model.h"

#include <QtMath>

namespace {
constexpr int kSampleCount = 475;
}

SpectrumModel::SpectrumModel(QObject *parent)
    : QObject(parent),
      m_samples(kSampleCount, -150.0f),
      m_phase(0.0f),
      m_dbmMin(-160.0f),
      m_dbmMax(-80.0f) {
    m_timer.setInterval(40);
    m_timer.setTimerType(Qt::PreciseTimer);
    connect(&m_timer, &QTimer::timeout, this, &SpectrumModel::generateTestData);
}

const QVector<float> &SpectrumModel::samples() const {
    return m_samples;
}

float SpectrumModel::dbmMin() const {
    return m_dbmMin;
}

float SpectrumModel::dbmMax() const {
    return m_dbmMax;
}

void SpectrumModel::start() {
    if (!m_timer.isActive()) {
        m_timer.start();
    }
}

void SpectrumModel::stop() {
    if (m_timer.isActive()) {
        m_timer.stop();
    }
}

void SpectrumModel::setSamples(const QVector<float> &samples) {
    if (samples.isEmpty()) {
        return;
    }
    if (samples.size() == m_samples.size()) {
        m_samples = samples;
    } else {
        m_samples.resize(samples.size());
        m_samples = samples;
    }
    emit samplesChanged();
}

void SpectrumModel::generateTestData() {
    const int count = m_samples.size();
    if (count == 0) {
        return;
    }

    const float center = (qSin(m_phase) * 0.5f + 0.5f) * (count - 1);
    const float width = 6.0f;

    for (int i = 0; i < count; ++i) {
        const float noise = -155.0f + 4.0f * qSin(m_phase + i * 0.12f);
        const float dist = qAbs(i - center);
        float peak = -80.0f - dist * 4.0f;
        if (dist > width) {
            peak = -160.0f;
        }
        m_samples[i] = qMax(noise, peak);
    }

    m_phase += 0.08f;
    if (m_phase > 1000.0f) {
        m_phase = 0.0f;
    }

    emit samplesChanged();
}
