import { Badge } from '@/components/ui/Badge';
import { SEVERITY_COLORS, type Severity } from '@/lib/constants';

interface SeverityBadgeProps {
  severity: Severity;
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return (
    <Badge color={SEVERITY_COLORS[severity]}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </Badge>
  );
}
