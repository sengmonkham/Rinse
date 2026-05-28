import React from 'react';
import type { TrendAlert } from '../types';
import { BrandIcon } from './BrandIcon';

interface AlertNotificationProps {
  alerts: TrendAlert[];
  onDismiss: (alertId: string) => void;
  onViewTrend?: (trendId: string) => void;
  onViewLead?: () => void;
}

const SEVERITY_ICONS: Record<string, string> = {
  critical: '🔴',
  high: '🟠',
  medium: '🟡',
  low: '🔵',
};

export const AlertNotification: React.FC<AlertNotificationProps> = ({
  alerts,
  onDismiss,
  onViewTrend,
  onViewLead,
}) => {
  // Show only most recent 4 un-dismissed alerts
  const visible = alerts.filter(a => !a.dismissed).slice(0, 4);

  if (visible.length === 0) return null;

  return (
    <div className="alert-stack">
      {visible.map(alert => (
        <div key={alert.id} className={`alert-toast severity-${alert.severity}`}>
          <div className="alert-toast-top">
            <div className="alert-toast-title">
              {SEVERITY_ICONS[alert.severity]}{' '}
              {alert.type === 'hot_lead' ? '🎯 HOT LEAD DETECTED' : alert.title}
            </div>
            <button className="alert-toast-close" onClick={() => onDismiss(alert.id)}>✕</button>
          </div>

          <div className="alert-toast-message">
            {alert.trend && (
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.3rem' }}>
                <BrandIcon platform={alert.trend.platformOrigin} size={12} />
                {alert.message}
              </span>
            )}
            {alert.type === 'hot_lead' && (
              <span>{alert.message}</span>
            )}
            {alert.accountsInvolved.length > 0 && (
              <div style={{ marginTop: '0.3rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Accounts: {alert.accountsInvolved.join(' · ')}
              </div>
            )}
          </div>

          <div className="alert-toast-footer">
            <span>{alert.triggeredAt}</span>
            <div className="alert-toast-actions">
              <button onClick={() => onDismiss(alert.id)}>Dismiss</button>
              {alert.trend && onViewTrend && (
                <button
                  className="primary-action"
                  onClick={() => { onViewTrend(alert.trend!.id); onDismiss(alert.id); }}
                >
                  View Trend →
                </button>
              )}
              {alert.type === 'hot_lead' && onViewLead && (
                <button className="primary-action" onClick={() => { onViewLead(); onDismiss(alert.id); }}>
                  View Lead →
                </button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
