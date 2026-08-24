# Task 4: Cost Analysis & Optimization

## Overview

Comprehensive cost analysis of NimbusTech's AWS environment with 6 concrete optimization recommendations delivering **41% cost reduction** ($173/month savings).

## Summary

**Current monthly spend:** $420  
**Optimized monthly spend:** $247  
**Total savings:** $173/month ($2,076/year)

## Files

- `cost-analysis.md` - Detailed cost breakdown and 6 optimization recommendations
- `billing-alarm.tf` - CloudWatch billing alarm for $350 threshold
- `README.md` - This file

## Top 3 Cost Drivers

1. **NAT Gateway** ($104/month, 24.8%) - High data processing costs
2. **Data Transfer Out** ($92.40/month, 22.0%) - Large API responses
3. **CloudWatch Logs** ($62.50/month, 14.9%) - Excessive logging

## Quick Wins

These can be implemented immediately with minimal risk:

### 1. Set CloudWatch Log Retention (5 minutes, $54/month savings)

```bash
# Current: Indefinite retention (expensive)
# Target: 30 days

aws logs put-retention-policy \
  --log-group-name /aws/ec2/nimbustech/application \
  --retention-in-days 30
```

### 2. Change Application Log Level (10 minutes, $40/month savings)

```javascript
// In application code
// Before:
logger.level = 'debug';  // Too verbose for production

// After:
logger.level = process.env.LOG_LEVEL || 'info';  // Only info, warn, error
```

### 3. Implement S3 Lifecycle Policies (10 minutes, $11/month savings)

```bash
cd task-4-cost-optimization
# Create lifecycle-policy.json (see cost-analysis.md for template)
aws s3api put-bucket-lifecycle-configuration \
  --bucket nimbus-uploads \
  --lifecycle-configuration file://lifecycle-policy.json
```

**Total Quick Wins: $105/month savings in 25 minutes**

## Medium-Term Optimizations

### 4. Purchase Reserved Instances (30 minutes, $51/month savings)

```bash
# EC2 Reserved Instances (1-year, No Upfront)
aws ec2 purchase-reserved-instances-offering \
  --reserved-instances-offering-id <offering-id> \
  --instance-count 2

# RDS Reserved Instance (1-year, No Upfront)
aws rds purchase-reserved-db-instances-offering \
  --reserved-db-instances-offering-id <offering-id> \
  --db-instance-count 1
```

### 5. Add VPC Endpoints (2 hours, $64/month savings)

```hcl
# S3 VPC Endpoint (Gateway, free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.us-east-1.s3"
}

# Reduces NAT Gateway data processing by 60%
```

## Advanced Optimizations

### 6. Deploy CloudFront CDN (4 hours, $62/month savings)

See `cost-analysis.md` for full CloudFront configuration. Benefits:
- Response compression (70% size reduction)
- Edge caching (80% origin request reduction)
- Lower data transfer costs ($0.085/GB vs $0.09)

## Billing Alarm Setup

Deploy the CloudWatch billing alarm:

```bash
cd task-4-cost-optimization

# 1. Enable billing alerts (one-time setup)
# Go to AWS Console → Account Settings → Billing Preferences
# Check "Receive Billing Alerts" → Save preferences

# 2. Deploy billing alarm
terraform init
terraform plan
terraform apply

# 3. Confirm SNS email subscription
# Check inbox for confirmation email from AWS

# 4. Test the alarm
aws cloudwatch set-alarm-state \
  --alarm-name nimbustech-billing-350-usd \
  --state-value ALARM \
  --state-reason "Testing" \
  --region us-east-1

# You should receive an email alert
```

## Cost Tagging Strategy

Implement these tag keys for all resources:

```hcl
default_tags {
  tags = {
    Client      = "NimbusTech"       # For multi-client billing
    Project     = "WebApp"           # Sub-project within client
    Environment = "Production"       # prod/staging/dev
    CostCenter  = "Engineering"      # Department chargeback
    Team        = "Platform"         # Team ownership
    Owner       = "john@example.com" # Primary contact
    ManagedBy   = "Terraform"        # How it's managed
  }
}
```

### Enable Cost Allocation Tags

```bash
aws ce update-cost-allocation-tags-status \
  --cost-allocation-tags-status \
    TagKey=Client,Status=Active \
    TagKey=Environment,Status=Active \
    TagKey=CostCenter,Status=Active
```

### Generate Cost Reports by Tag

```bash
# Cost by client
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Client \
  --output table

# Cost by environment
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Environment \
  --output table
```

## Monthly Cost Review Process

### Week 1: Review Spend

```bash
# 1. Get last month's costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d 'last month' +%Y-%m-01),End=$(date +%Y-%m-01) \
  --granularity MONTHLY \
  --metrics BlendedCost UsageQuantity \
  --group-by Type=SERVICE

# 2. Identify top 5 cost drivers
# 3. Compare to previous month (trend analysis)
# 4. Investigate any >20% increases
```

### Week 2: Optimization Actions

```bash
# 1. Check for unused resources
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=stopped" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],State.Name]' \
  --output table

# 2. Check for unattached EBS volumes
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query 'Volumes[*].[VolumeId,Size,VolumeType]' \
  --output table

# 3. Check for old snapshots
aws ec2 describe-snapshots \
  --owner-ids self \
  --query 'Snapshots[?StartTime<`2026-06-01`].[SnapshotId,VolumeSize,StartTime]' \
  --output table
```

### Week 3: Reserved Instance Optimization

```bash
# 1. Check RI utilization
aws ce get-reservation-utilization \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY

# 2. Check RI coverage
aws ce get-reservation-coverage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY

# 3. Get RI recommendations
aws ce get-reservation-purchase-recommendation \
  --service EC2 \
  --payment-option NO_UPFRONT \
  --term-in-years ONE_YEAR
```

### Week 4: Reporting

Create monthly cost report:
1. Total spend vs budget
2. Top 3 services by cost
3. Cost trends (MoM % change)
4. Optimization actions taken
5. Projected savings

## Monitoring & Alerting

### CloudWatch Dashboard

Create a cost monitoring dashboard:

```bash
# Create dashboard
aws cloudwatch put-dashboard --dashboard-name NimbusTech-Costs \
  --dashboard-body file://cost-dashboard.json
```

### Cost Anomaly Detection

```bash
# Enable Cost Anomaly Detection
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "MonitorName": "NimbusTech-Spend-Monitor",
    "MonitorType": "DIMENSIONAL",
    "MonitorDimension": "SERVICE"
  }'

# Get monitor ARN from output, then create subscription
aws ce create-anomaly-subscription \
  --anomaly-subscription '{
    "SubscriptionName": "Daily-Anomaly-Alerts",
    "Threshold": 100,
    "Frequency": "DAILY",
    "MonitorArnList": ["<monitor-arn>"],
    "Subscribers": [{"Address": "finance@nimbustech.com", "Type": "EMAIL"}]
  }'
```

## Implementation Timeline

### Week 1: Quick Wins
- [ ] Deploy billing alarm
- [ ] Set log retention policies
- [ ] Change application log level
- [ ] Implement S3 lifecycle policies

**Expected savings:** $105/month

### Week 2-3: Infrastructure
- [ ] Purchase EC2 Reserved Instances
- [ ] Purchase RDS Reserved Instance
- [ ] Deploy S3 VPC endpoint
- [ ] Audit NAT Gateway traffic

**Expected savings:** $115/month (cumulative: $220/month)

### Month 2: Advanced
- [ ] Deploy CloudFront CDN
- [ ] Implement response compression
- [ ] Test RDS right-sizing
- [ ] Set up cost anomaly detection

**Expected savings:** Additional $60/month (cumulative: $280/month)

### Ongoing
- [ ] Monthly cost review meetings
- [ ] Quarterly RI optimization
- [ ] Continuous right-sizing

## ROI Analysis

| Metric | Value |
|--------|-------|
| Current annual cost | $5,040 |
| Optimized annual cost | $2,964 |
| Annual savings | $2,076 |
| Implementation time | 40 hours |
| Engineering cost (@ $150/hr) | $6,000 |
| Payback period | 2.9 months |
| 1-year ROI | 35% |
| 3-year ROI | 204% |

## Verification Commands

### Check Current Spend

```bash
# Get current month-to-date spend
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --output json | jq '.ResultsByTime[0].Total.BlendedCost.Amount'
```

### Check NAT Gateway Data Processing

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination \
  --dimensions Name=NatGatewayId,Value=<nat-gateway-id> \
  --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 2592000 \
  --statistics Sum \
  | jq '.Datapoints[0].Sum / 1024 / 1024 / 1024'  # Convert to GB
```

### Check CloudWatch Logs Ingestion

```bash
# Get log group size
aws logs describe-log-groups \
  --log-group-name-prefix /aws/ec2/nimbustech \
  --query 'logGroups[*].[logGroupName,storedBytes]' \
  --output table
```

## Troubleshooting

### Billing Alarm Not Triggering

**Issue:** Alarm state shows "INSUFFICIENT_DATA"

**Solution:**
1. Verify billing alerts are enabled in AWS Account Settings
2. Wait 6 hours for first datapoint
3. Check metric exists:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Billing \
     --metric-name EstimatedCharges \
     --dimensions Name=Currency,Value=USD \
     --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 86400 \
     --statistics Maximum \
     --region us-east-1
   ```

### SNS Email Not Received

**Issue:** No confirmation email after Terraform apply

**Solution:**
1. Check spam folder
2. Verify email address in subscription:
   ```bash
   aws sns list-subscriptions-by-topic \
     --topic-arn <topic-arn> \
     --region us-east-1
   ```
3. Manually subscribe:
   ```bash
   aws sns subscribe \
     --topic-arn <topic-arn> \
     --protocol email \
     --notification-endpoint your-email@example.com \
     --region us-east-1
   ```

### Cost Reports Show Different Numbers

**Issue:** AWS Cost Explorer shows different costs than CloudWatch billing metrics

**Explanation:**
- CloudWatch Billing: Estimated charges, updated every 6 hours
- Cost Explorer: Actual finalized charges, updated daily
- Use Cost Explorer for accurate historical data

## Additional Resources

- [AWS Cost Optimization Best Practices](https://aws.amazon.com/pricing/cost-optimization/)
- [AWS Well-Architected Cost Optimization Pillar](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/)
- [AWS Compute Optimizer](https://aws.amazon.com/compute-optimizer/) - Automated right-sizing
- [AWS Trusted Advisor](https://aws.amazon.com/premiumsupport/technology/trusted-advisor/) - Cost recommendations
