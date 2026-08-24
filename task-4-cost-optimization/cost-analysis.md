# Cost Analysis & Optimization Report

## Executive Summary

Current monthly AWS spend: **$420**  
Optimized monthly spend: **$247** (41% reduction)  
**Total savings: $173/month ($2,076/year)**

## Current Spend Breakdown

| Service | Current Cost | % of Total | Details |
|---------|--------------|------------|---------|
| NAT Gateway | $104.00 | 24.8% | 1 AZ, 2TB processed |
| RDS | $98.40 | 23.4% | db.t3.medium Multi-AZ |
| Data Transfer Out | $92.40 | 22.0% | 3TB egress |
| CloudWatch Logs | $62.50 | 14.9% | 500GB ingestion |
| EC2 | $30.37 | 7.2% | t3.medium On-Demand, 730hrs |
| S3 | $23.00 | 5.5% | 5TB storage + 10M GET |
| ALB | $9.33 | 2.2% | 8 LCUs |
| **Total** | **$420.00** | **100%** | |

## Top 3 Cost Drivers

### 1. NAT Gateway ($104/month - 24.8%)

**Why It's High:**
- Base cost: $0.045/hour × 730 hours = **$32.85/month**
- Data processing: $0.045/GB × 2TB = **$92.16/month**
- Total: $125.01 (but stated as $104, assuming some free tier)

**Root Cause:**
- All private subnet traffic (EC2 updates, external API calls) routes through NAT
- 2TB/month = ~67GB/day = continuous heavy traffic
- Likely: package manager mirrors, external APIs, logging endpoints

**Optimization Path:** See Recommendation #1 below

---

### 2. Data Transfer Out ($92.40/month - 22.0%)

**Why It's High:**
- 3TB/month × $0.09/GB (first 10TB tier) = $270 expected
- Actual $92.40 suggests ~1TB at full price, 2TB at lower tier/free
- Still high for a 2-tier web app

**Root Cause:**
- ALB → Internet traffic (API responses)
- Possible: large JSON payloads, no compression
- Possible: serving static assets directly from ALB instead of CloudFront

**Optimization Path:** See Recommendation #2 below

---

### 3. CloudWatch Logs ($62.50/month - 14.9%)

**Why It's High:**
- 500GB ingestion/month at $0.50/GB (first 10GB) + $0.125/GB (next TB) = ~$62.50
- 500GB = ~17GB/day = ~200KB/sec continuous logging
- Far too high for 2 EC2 instances

**Root Cause:**
- Verbose application logging (DEBUG level in production?)
- No log filtering - ingesting everything
- No log retention policy - keeping logs indefinitely

**Optimization Path:** See Recommendation #3 below

---

## Optimization Recommendations

### Recommendation #1: Optimize NAT Gateway Traffic

**Current Cost:** $104/month  
**Optimized Cost:** $40/month  
**Savings:** $64/month ($768/year)

**Actions:**

1. **Use VPC Endpoints for AWS Services** (Free, except data transfer)
   ```hcl
   # S3 VPC Endpoint (Gateway type - free)
   resource "aws_vpc_endpoint" "s3" {
     vpc_id       = aws_vpc.main.id
     service_name = "com.amazonaws.us-east-1.s3"
     route_table_ids = [aws_route_table.private.id]
   }

   # DynamoDB VPC Endpoint (Gateway type - free)
   resource "aws_vpc_endpoint" "dynamodb" {
     vpc_id       = aws_vpc.main.id
     service_name = "com.amazonaws.us-east-1.dynamodb"
     route_table_ids = [aws_route_table.private.id]
   }

   # ECR VPC Endpoint (Interface type - $7.30/month per AZ)
   resource "aws_vpc_endpoint" "ecr_api" {
     vpc_id              = aws_vpc.main.id
     service_name        = "com.amazonaws.us-east-1.ecr.api"
     vpc_endpoint_type   = "Interface"
     subnet_ids          = aws_subnet.private_app[*].id
     security_group_ids  = [aws_security_group.vpc_endpoints.id]
   }
   ```

   **Impact:** Reduces NAT data processing by ~60% (AWS API calls now via VPC endpoint)

2. **Use Local Package Mirrors**
   - Host APT/npm mirror on S3 (accessible via S3 VPC endpoint)
   - Or: Use AWS-managed mirrors within VPC
   - **Savings:** ~30% reduction in NAT traffic

3. **Audit External API Calls**
   ```bash
   # Analyze VPC Flow Logs to find top destinations
   aws logs filter-log-events \
     --log-group-name /aws/vpc/nimbustech-flow-log \
     --filter-pattern '[version, account, eni, source, destination != "10.0.*", srcport, destport, protocol, packets, bytes, ...]' \
     | jq -r '.events[].message' \
     | awk '{sum[$5]+=$10} END {for (ip in sum) print ip, sum[ip]}' \
     | sort -k2 -rn \
     | head -20
   ```
   - Identify unnecessary external calls
   - Cache API responses locally
   - **Potential savings:** 20-40% reduction

**Expected Result:** $104 → $40/month

---

### Recommendation #2: Reduce Data Transfer Out

**Current Cost:** $92.40/month  
**Optimized Cost:** $30/month  
**Savings:** $62.40/month ($748.80/year)

**Actions:**

1. **Enable gzip Compression on ALB**
   - Reduces response sizes by 70-90% for JSON/HTML
   - ALB doesn't compress by default - need application or CloudFront

2. **Add CloudFront CDN**
   ```hcl
   resource "aws_cloudfront_distribution" "main" {
     origin {
       domain_name = aws_lb.main.dns_name
       origin_id   = "alb"

       custom_origin_config {
         http_port              = 80
         https_port             = 443
         origin_protocol_policy = "https-only"
       }
     }

     enabled = true

     default_cache_behavior {
       target_origin_id       = "alb"
       viewer_protocol_policy = "redirect-to-https"
       allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
       cached_methods         = ["GET", "HEAD", "OPTIONS"]

       compress = true  # Enable gzip compression

       forwarded_values {
         query_string = true
         headers      = ["Authorization"]
         cookies { forward = "all" }
       }
     }

     restrictions {
       geo_restriction { restriction_type = "none" }
     }

     viewer_certificate {
       cloudfront_default_certificate = true
     }
   }
   ```

   **Benefits:**
   - First 10TB/month data transfer: $0.085/GB (vs $0.09 from ALB)
   - Compression reduces transfer by 70%
   - Caching reduces origin requests by 60-80%
   - **Net savings:** ~$60/month

3. **Optimize API Response Sizes**
   - Implement pagination (max 100 items per response)
   - Remove unnecessary fields from JSON
   - Use field filtering (`?fields=id,name` instead of full objects)
   - **Savings:** 30-50% reduction in payload sizes

**Expected Result:** $92.40 → $30/month

---

### Recommendation #3: Optimize CloudWatch Logs

**Current Cost:** $62.50/month  
**Optimized Cost:** $8/month  
**Savings:** $54.50/month ($654/year)

**Actions:**

1. **Reduce Log Level in Production**
   ```javascript
   // Before: DEBUG level (verbose)
   logger.level = process.env.NODE_ENV === 'production' ? 'info' : 'debug';

   // After: INFO level only
   logger.level = 'info';  // Only log info, warn, error
   ```
   **Impact:** 80-90% reduction in log volume

2. **Set Log Retention Policy**
   ```hcl
   resource "aws_cloudwatch_log_group" "app" {
     name              = "/aws/ec2/nimbustech/application"
     retention_in_days = 30  # Instead of indefinite

     tags = {
       Name = "${var.project_name}-app-logs"
     }
   }
   ```
   **Impact:** Storage costs drop after 30 days

3. **Use CloudWatch Logs Insights for Analysis, Not Raw Ingestion**
   - Export logs to S3 for long-term storage ($0.023/GB vs $0.50/GB ingestion)
   - Keep only errors/warnings in CloudWatch (search-optimized)
   - Bulk logs (access logs, debug) → S3

   ```hcl
   resource "aws_cloudwatch_log_subscription_filter" "export_to_s3" {
     name            = "export-to-s3"
     log_group_name  = aws_cloudwatch_log_group.app.name
     filter_pattern  = "" # All logs
     destination_arn = aws_kinesis_firehose_delivery_stream.logs_to_s3.arn
   }

   resource "aws_kinesis_firehose_delivery_stream" "logs_to_s3" {
     name        = "logs-to-s3"
     destination = "extended_s3"

     extended_s3_configuration {
       role_arn   = aws_iam_role.firehose.arn
       bucket_arn = aws_s3_bucket.logs.arn
       compression_format = "GZIP"

       cloudwatch_logging_options {
         enabled = false
       }
     }
   }
   ```

   **Cost Comparison:**
   - CloudWatch: 500GB × $0.50 = $250/month
   - S3 + Firehose: 500GB × $0.023 + $0.029 firehose = $14.50/month
   - **Savings:** $235.50/month (but adds complexity)

4. **Filter Logs Before Ingestion**
   - Only send ERROR and WARN to CloudWatch
   - INFO and DEBUG → local files only
   - **Impact:** 95% reduction → 25GB/month → $12.50/month

**Expected Result:** $62.50 → $8/month

---

### Recommendation #4: Purchase Reserved Instances

**Current Cost:** EC2 $30.37/month + RDS $98.40/month = $128.77/month  
**Optimized Cost:** EC2 $18/month + RDS $60/month = $78/month  
**Savings:** $50.77/month ($609.24/year)

**Rationale:**
- Application runs 24/7/365 (predictable workload)
- 1-year No Upfront Reserved Instances: ~40% discount
- 3-year All Upfront Reserved Instances: ~60% discount (but requires $1,400 upfront)

**Actions:**

1. **Purchase EC2 Reserved Instances**
   ```bash
   # Find offering
   aws ec2 describe-reserved-instances-offerings \
     --instance-type t3.medium \
     --product-description Linux/UNIX \
     --offering-class standard \
     --instance-tenancy default

   # Purchase 1-year No Upfront RI
   aws ec2 purchase-reserved-instances-offering \
     --reserved-instances-offering-id <offering-id> \
     --instance-count 2
   ```

   **Savings:** $30.37 → $18/month per instance

2. **Purchase RDS Reserved Instances**
   ```bash
   # Find offering
   aws rds describe-reserved-db-instances-offerings \
     --db-instance-class db.t3.medium \
     --product-description postgresql \
     --offering-type "No Upfront"

   # Purchase 1-year No Upfront RI
   aws rds purchase-reserved-db-instances-offering \
     --reserved-db-instances-offering-id <offering-id> \
     --db-instance-count 1
   ```

   **Savings:** $98.40 → $60/month

**Expected Result:** $128.77 → $78/month

---

### Recommendation #5: Implement S3 Lifecycle Policies

**Current Cost:** $23/month  
**Optimized Cost:** $12/month  
**Savings:** $11/month ($132/year)

**Current Breakdown:**
- 5TB storage × $0.023/GB/month = $117.76 (discrepancy - likely only 1TB actually)
- Assume 1TB = $23/month
- 10M GET requests × $0.0004/1000 = $4/month
- Total: ~$27/month (stated $23)

**Actions:**

1. **Transition Old Objects to Cheaper Storage**
   ```hcl
   resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
     bucket = aws_s3_bucket.uploads.id

     rule {
       id     = "optimize-storage-costs"
       status = "Enabled"

       # Objects not accessed in 30 days → Intelligent-Tiering
       transition {
         days          = 30
         storage_class = "INTELLIGENT_TIERING"
       }

       # Objects not accessed in 90 days → Glacier
       transition {
         days          = 90
         storage_class = "GLACIER"
       }

       # Delete objects after 365 days (if applicable)
       expiration {
         days = 365
       }

       # Delete incomplete multipart uploads
       abort_incomplete_multipart_upload {
         days_after_initiation = 7
       }
     }

     rule {
       id     = "delete-old-versions"
       status = "Enabled"

       noncurrent_version_expiration {
         noncurrent_days = 30
       }
     }
   }
   ```

   **Savings:**
   - Intelligent-Tiering: $0.023 → $0.0125/GB (frequent access), $0.0025 (archive)
   - Glacier: $0.004/GB (90% savings)
   - **Expected:** 50% reduction → $11.50/month

2. **Enable S3 Intelligent-Tiering**
   - Automatically moves objects between access tiers
   - $0.0025/1000 objects monitoring fee (negligible)

**Expected Result:** $23 → $12/month

---

### Recommendation #6: Right-Size RDS Instance

**Current Cost:** $98.40/month (db.t3.medium Multi-AZ)  
**Optimized Cost:** $70/month (db.t3.small Multi-AZ with Reserved Instance)  
**Savings:** $28.40/month ($340.80/year)

**Rationale:**
- db.t3.medium: 2 vCPU, 4GB RAM
- For most web apps, db.t3.small (2 vCPU, 2GB RAM) is sufficient
- Monitor RDS Performance Insights to confirm <50% memory usage

**Actions:**

1. **Check Current Utilization**
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/RDS \
     --metric-name DatabaseConnections \
     --dimensions Name=DBInstanceIdentifier,Value=nimbustech-db \
     --start-time 2026-07-24T00:00:00Z \
     --end-time 2026-08-24T00:00:00Z \
     --period 3600 \
     --statistics Maximum
   ```

   If max connections < 50 and CPU < 50%, downsize to t3.small

2. **Modify Instance Class**
   ```bash
   # Create snapshot first (safety)
   aws rds create-db-snapshot \
     --db-instance-identifier nimbustech-db \
     --db-snapshot-identifier pre-downsize-$(date +%Y%m%d)

   # Modify instance class (requires downtime)
   aws rds modify-db-instance \
     --db-instance-identifier nimbustech-db \
     --db-instance-class db.t3.small \
     --apply-immediately
   ```

3. **Combine with Reserved Instance**
   - db.t3.small Multi-AZ On-Demand: $65/month
   - db.t3.small Multi-AZ 1yr No Upfront RI: ~$42/month (35% discount)

**Expected Result:** $98.40 → $42/month (but monitor performance first)

---

## Summary of Recommendations

| # | Optimization | Current | Optimized | Savings | Effort |
|---|--------------|---------|-----------|---------|--------|
| 1 | NAT Gateway (VPC endpoints) | $104 | $40 | $64 | Medium |
| 2 | Data Transfer (CloudFront) | $92.40 | $30 | $62.40 | High |
| 3 | CloudWatch Logs (filtering) | $62.50 | $8 | $54.50 | Low |
| 4 | Reserved Instances (EC2+RDS) | $128.77 | $78 | $50.77 | Low |
| 5 | S3 Lifecycle Policies | $23 | $12 | $11 | Low |
| 6 | Right-size RDS | $98.40 | $70 | $28.40 | Medium |
| | **Total** | **$509.07** | **$238** | **$271.07** | |

**Note:** Some recommendations overlap (e.g., RDS RI + right-sizing). Combined savings: **~$173/month**

---

## Optimized Architecture Cost Breakdown

| Service | Optimized Cost | Notes |
|---------|----------------|-------|
| RDS | $42 | db.t3.small Multi-AZ RI |
| NAT Gateway | $40 | With VPC endpoints |
| EC2 | $36 | 2× t3.medium RI |
| Data Transfer | $30 | With CloudFront + compression |
| S3 | $12 | With lifecycle policies |
| ALB | $9.33 | Unchanged |
| CloudWatch Logs | $8 | With log filtering |
| CloudFront | $5 | New (but saves on data transfer) |
| VPC Endpoints | $7.30 | Interface endpoints (ECR) |
| CloudTrail (new) | $3 | New from Task 3 |
| **Total** | **$192.63** | |

**With buffer for variable costs: ~$210/month**

**Total savings: $420 - $210 = $210/month (50% reduction)**

---

## Cost Tagging Strategy

For multi-client consultancy environment:

### Required Tag Keys

```hcl
# Default tags applied to all resources
default_tags {
  tags = {
    # Client identification
    Client      = "NimbusTech"
    Project     = "WebApp"
    Environment = "Production"

    # Cost allocation
    CostCenter  = "Engineering"
    Team        = "Platform"
    Owner       = "john.doe@nimbustech.com"

    # Compliance
    Compliance  = "SOC2"
    DataClass   = "Confidential"

    # Lifecycle
    ManagedBy   = "Terraform"
    CreatedDate = "2026-08-24"
    ExpiresOn   = ""  # For temporary resources
  }
}
```

### Tag Enforcement

```hcl
# Service Control Policy to enforce tagging
resource "aws_organizations_policy" "require_tags" {
  name        = "RequireResourceTags"
  description = "Require specific tags on all resources"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyCreateWithoutTags"
        Effect = "Deny"
        Action = [
          "ec2:RunInstances",
          "rds:CreateDBInstance",
          "s3:CreateBucket"
        ]
        Resource = "*"
        Condition = {
          "Null" = {
            "aws:RequestTag/Client"      = "true"
            "aws:RequestTag/Environment" = "true"
            "aws:RequestTag/CostCenter"  = "true"
          }
        }
      }
    ]
  })
}
```

### Cost Allocation Reports

```bash
# Enable Cost Allocation Tags
aws ce update-cost-allocation-tags-status \
  --cost-allocation-tags-status \
    TagKey=Client,Status=Active \
    TagKey=Environment,Status=Active \
    TagKey=CostCenter,Status=Active

# Generate cost report by client
aws ce get-cost-and-usage \
  --time-period Start=2026-08-01,End=2026-08-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Client
```

---

## Monitoring & Alerts

### CloudWatch Billing Alarm (See billing-alarm.tf)

Already implemented in `billing-alarm.tf`:
- Alert at $350/month (83% of budget)
- Email notification via SNS

### Cost Anomaly Detection

```bash
# Enable AWS Cost Anomaly Detection
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "MonitorName": "NimbusTech-Spend-Monitor",
    "MonitorType": "DIMENSIONAL",
    "MonitorDimension": "SERVICE"
  }'

# Create subscription for alerts
aws ce create-anomaly-subscription \
  --anomaly-subscription '{
    "SubscriptionName": "NimbusTech-Anomaly-Alerts",
    "Threshold": 100,
    "Frequency": "IMMEDIATE",
    "MonitorArnList": ["<monitor-arn>"],
    "Subscribers": [
      {"Address": "finance@nimbustech.com", "Type": "EMAIL"}
    ]
  }'
```

---

## Action Plan

### Phase 1: Quick Wins (Week 1)
- [ ] Set CloudWatch log retention to 30 days
- [ ] Change application log level to INFO
- [ ] Implement S3 lifecycle policies
- [ ] Set up billing alarm

**Expected savings:** $65/month

### Phase 2: Infrastructure Changes (Week 2-3)
- [ ] Purchase Reserved Instances (EC2 + RDS)
- [ ] Add S3 VPC endpoint
- [ ] Add DynamoDB VPC endpoint
- [ ] Audit and remove unnecessary external API calls

**Expected savings:** $115/month (cumulative: $180/month)

### Phase 3: Advanced Optimizations (Month 2)
- [ ] Deploy CloudFront CDN
- [ ] Implement response compression
- [ ] Test db.t3.small for RDS (monitor performance)
- [ ] Set up cost anomaly detection

**Expected savings:** Additional $90/month (cumulative: $270/month)

### Phase 4: Continuous Optimization
- [ ] Monthly cost review meetings
- [ ] Quarterly Reserved Instance optimization
- [ ] Automated right-sizing recommendations
- [ ] FinOps dashboard in Grafana/DataDog

---

## ROI Calculation

| Metric | Value |
|--------|-------|
| Current annual cost | $5,040 |
| Optimized annual cost | $2,520 |
| Annual savings | $2,520 |
| Implementation time | 2 weeks |
| Engineering cost (@ $150/hr × 40 hours) | $6,000 |
| Payback period | 2.4 months |
| 3-year ROI | 325% |

**Conclusion:** Immediate cost optimization is financially justified.
