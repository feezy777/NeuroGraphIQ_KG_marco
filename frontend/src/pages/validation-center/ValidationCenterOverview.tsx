import { useI18n } from '../../i18n-context'
import type { ValidationCenterTabId } from './validationCenterTypes'

interface Props {
  onNavigate: (tab: ValidationCenterTabId) => void
}

export function ValidationCenterOverview({ onNavigate }: Props) {
  const { t } = useI18n()

  const cards = [
    {
      key: 'rule-validation' as ValidationCenterTabId,
      title: t('validationCenter.ruleValidation'),
      desc: t('validationCenter.ruleValidationDesc'),
      color: '#3b82f6',
    },
    {
      key: 'human-review' as ValidationCenterTabId,
      title: t('validationCenter.humanReview'),
      desc: t('validationCenter.humanReviewDesc'),
      color: '#8b5cf6',
    },
    {
      key: 'promotion' as ValidationCenterTabId,
      title: t('validationCenter.promotion'),
      desc: t('validationCenter.promotionDesc'),
      color: '#10b981',
    },
    {
      key: 'mirror' as ValidationCenterTabId,
      title: t('validationCenter.mirror'),
      desc: t('validationCenter.mirrorDesc'),
      color: '#f59e0b',
    },
    {
      key: 'macro' as ValidationCenterTabId,
      title: t('validationCenter.macro'),
      desc: t('validationCenter.macroDesc'),
      color: '#ef4444',
    },
    {
      key: 'final' as ValidationCenterTabId,
      title: t('validationCenter.final'),
      desc: t('validationCenter.finalDesc'),
      color: '#06b6d4',
    },
  ]

  return (
    <div className="validation-overview">
      <div className="validation-overview-flow">
        <div className="validation-flow-label">{t('validationCenter.governanceFlow')}</div>
        <div className="validation-flow-cards">
          {cards.map((card) => (
            <button
              key={card.key}
              type="button"
              className="validation-flow-card"
              style={{ borderTopColor: card.color }}
              onClick={() => onNavigate(card.key)}
            >
              <div className="validation-flow-card-title" style={{ color: card.color }}>
                {card.title}
              </div>
              <div className="validation-flow-card-desc">{card.desc}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
