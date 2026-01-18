#include "spectrum_item.h"

#include "spectrum_model.h"

#include <QColor>
#include <QSGFlatColorMaterial>
#include <QSGGeometry>
#include <QSGGeometryNode>

SpectrumItem::SpectrumItem(QQuickItem *parent) : QQuickItem(parent), m_model(nullptr) {
    setFlag(ItemHasContents, true);
}

QObject *SpectrumItem::model() const {
    return m_model;
}

void SpectrumItem::setModel(QObject *model) {
    if (model == m_model) {
        return;
    }
    if (m_model) {
        disconnect(m_model, nullptr, this, nullptr);
    }
    m_model = qobject_cast<SpectrumModel *>(model);
    if (m_model) {
        connect(m_model, &SpectrumModel::samplesChanged, this, &SpectrumItem::update);
        connect(m_model, &SpectrumModel::rangeChanged, this, &SpectrumItem::update);
    }
    emit modelChanged();
    update();
}

QSGNode *SpectrumItem::updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *) {
    QSGGeometryNode *node = static_cast<QSGGeometryNode *>(oldNode);
    if (!node) {
        node = new QSGGeometryNode();
        auto *geometry = new QSGGeometry(QSGGeometry::defaultAttributes_Point2D(), 0);
        geometry->setDrawingMode(QSGGeometry::DrawLineStrip);
        node->setGeometry(geometry);
        node->setFlag(QSGNode::OwnsGeometry, true);

        auto *material = new QSGFlatColorMaterial();
        material->setColor(QColor(0, 255, 120));
        node->setMaterial(material);
        node->setFlag(QSGNode::OwnsMaterial, true);
    }

    if (!m_model) {
        return node;
    }

    const QVector<float> &samples = m_model->samples();
    const int count = samples.size();
    if (count < 2) {
        return node;
    }

    QSGGeometry *geometry = node->geometry();
    geometry->allocate(count);

    QSGGeometry::Point2D *vertices = geometry->vertexDataAsPoint2D();

    const float width = boundingRect().width();
    const float height = boundingRect().height();
    const float dbmMin = m_model->dbmMin();
    const float dbmMax = m_model->dbmMax();
    const float range = (dbmMax - dbmMin) > 0.001f ? (dbmMax - dbmMin) : 1.0f;

    for (int i = 0; i < count; ++i) {
        const float x = (count == 1) ? 0.0f : (width * i) / (count - 1);
        float norm = (samples[i] - dbmMin) / range;
        if (norm < 0.0f) {
            norm = 0.0f;
        }
        if (norm > 1.0f) {
            norm = 1.0f;
        }
        const float y = height * (1.0f - norm);
        vertices[i].set(x, y);
    }

    node->markDirty(QSGNode::DirtyGeometry);
    return node;
}
