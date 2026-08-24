# NimbusTech AWS Architecture Diagram

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 Internet                                     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 │ HTTPS/HTTP
                                 ▼
                    ┌────────────────────────┐
                    │   Internet Gateway     │
                    │       (IGW)            │
                    └────────────┬───────────┘
                                 │
                                 │
        ┌────────────────────────┴────────────────────────┐
        │                    VPC                          │
        │                 10.0.0.0/16                     │
        │                                                 │
        │  ┌──────────────────────────────────────────┐  │
        │  │         Public Subnets (ALB)             │  │
        │  │   us-east-1a      │      us-east-1b      │  │
        │  │   10.0.1.0/24     │      10.0.2.0/24     │  │
        │  │                   │                      │  │
        │  │     ┌─────────────┴─────────────┐        │  │
        │  │     │  Application Load Balancer│        │  │
        │  │     │   (Internet-facing)        │        │  │
        │  │     └─────────────┬─────────────┘        │  │
        │  └───────────────────┼──────────────────────┘  │
        │                      │                          │
        │                      │ Port 3000                │
        │                      ▼                          │
        │  ┌──────────────────────────────────────────┐  │
        │  │   Private Application Subnets (EC2)      │  │
        │  │   us-east-1a      │      us-east-1b      │  │
        │  │   10.0.11.0/24    │      10.0.12.0/24    │  │
        │  │                   │                      │  │
        │  │  ┌──────────┐     │     ┌──────────┐    │  │
        │  │  │ EC2 App  │     │     │ EC2 App  │    │  │
        │  │  │ Instance │     │     │ Instance │    │  │
        │  │  │ (t3.med) │     │     │ (t3.med) │    │  │
        │  │  └────┬─────┘     │     └────┬─────┘    │  │
        │  └───────┼────────────┼──────────┼──────────┘  │
        │          │            │          │              │
        │          │       Port 5432       │              │
        │          └────────────┼──────────┘              │
        │                       ▼                         │
        │  ┌──────────────────────────────────────────┐  │
        │  │  Private Database Subnets (RDS)          │  │
        │  │   us-east-1a      │      us-east-1b      │  │
        │  │   10.0.21.0/24    │      10.0.22.0/24    │  │
        │  │                   │                      │  │
        │  │     ┌─────────────┴─────────────┐        │  │
        │  │     │   RDS PostgreSQL 16        │        │  │
        │  │     │   (Multi-AZ, db.t3.med)    │        │  │
        │  │     │   Primary + Standby        │        │  │
        │  │     └───────────────────────────┘        │  │
        │  └──────────────────────────────────────────┘  │
        │                                                 │
        │  ┌──────────────────────────────────────────┐  │
        │  │              NAT Gateway                  │  │
        │  │          (us-east-1a only)                │  │
        │  └──────────────────────────────────────────┘  │
        │                      │                          │
        └──────────────────────┼──────────────────────────┘
                               │
                               ▼
                          Internet
                   (for updates & patches)
```

## Security Groups

### ALB Security Group
```
Ingress:
  - 0.0.0.0/0 → Port 80 (HTTP)
  - 0.0.0.0/0 → Port 443 (HTTPS)

Egress:
  - App-SG → Port 3000 (to application tier only)
```

### Application Security Group
```
Ingress:
  - ALB-SG → Port 3000 (from load balancer only)
  - NO SSH access (use SSM Session Manager)

Egress:
  - RDS-SG → Port 5432 (to database only)
  - 0.0.0.0/0 → Port 443 (HTTPS for updates)
  - 0.0.0.0/0 → Port 80 (HTTP for package managers)
```

### RDS Security Group
```
Ingress:
  - App-SG → Port 5432 (from application tier only)

Egress:
  - None (RDS doesn't initiate outbound connections)
```

## Network Flow

### Public Traffic Flow
1. User → Internet → Internet Gateway
2. Internet Gateway → ALB (public subnets)
3. ALB → EC2 instances (private app subnets)
4. EC2 → RDS (private DB subnets)
5. Response: RDS → EC2 → ALB → IGW → User

### Outbound Traffic Flow (Updates)
1. EC2 (private subnet) → NAT Gateway (public subnet)
2. NAT Gateway → Internet Gateway → Internet
3. Used for: apt-get updates, npm packages, external API calls

### Admin Access Flow
1. Admin → AWS Console/CLI
2. SSM Session Manager → EC2 (no SSH port 22)
3. Session encrypted via TLS, logged in CloudTrail

## Key Design Decisions

### Multi-AZ Deployment
- **Public subnets** in 2 AZs for ALB high availability
- **Private app subnets** in 2 AZs for EC2 redundancy
- **Private DB subnets** in 2 AZs for RDS Multi-AZ failover
- **NAT Gateway** in single AZ (cost tradeoff - see README)

### Network Segmentation
- **Public tier**: Only ALB exposed to internet
- **Private app tier**: EC2 instances have no public IPs, no direct internet access
- **Private DB tier**: RDS completely isolated, only accessible from app tier

### Security Controls
- **No SSH ingress**: Use SSM Session Manager for instance access
- **IMDSv2 enforced**: Prevents SSRF attacks on instance metadata
- **Least-privilege SGs**: Each tier can only talk to what it needs
- **Encryption**: RDS storage encryption, EBS volume encryption

### High Availability
- **ALB**: Distributes traffic across multiple AZs
- **EC2**: Instances in multiple AZs (ready for Auto Scaling Group)
- **RDS Multi-AZ**: Automatic failover to standby in another AZ

### Cost Optimizations
- **Single NAT Gateway**: $32/month vs $64 for Multi-AZ (tradeoff documented)
- **gp3 storage**: Better price/performance than gp2
- **Right-sized instances**: t3.medium (2 vCPU, 4GB RAM)
- **CloudWatch log retention**: 30-90 days, not indefinite

## Monitoring & Logging

### CloudWatch
- VPC Flow Logs → `/aws/vpc/nimbustech-flow-log`
- Application Logs → `/aws/ec2/nimbustech/application`
- RDS Logs → CloudWatch Logs Exports (PostgreSQL, upgrade)

### Enhanced Monitoring
- EC2: Detailed CloudWatch monitoring enabled
- RDS: Performance Insights (7 days free tier)
- RDS: Enhanced monitoring (60-second granularity)

## Disaster Recovery

### Backup Strategy
- **RDS**: Automated daily backups, 7-day retention
- **RDS**: Backup window 03:00-04:00 UTC
- **Snapshots**: Manual snapshots before major changes

### Recovery Capabilities
- **RDS Multi-AZ**: Automatic failover in <2 minutes
- **Point-in-Time Recovery**: Restore to any second within retention period
- **AMI backups**: Create AMIs of EC2 instances before changes

## Future Enhancements

1. **Auto Scaling Group**: Replace static EC2 instances with ASG for elasticity
2. **Multi-Region**: Add us-west-2 deployment with Route 53 failover
3. **AWS WAF**: Add WAF rules on ALB for SQL injection/XSS protection
4. **CloudFront**: Add CDN for static assets and DDoS protection
5. **RDS Proxy**: Add connection pooling for Lambda integration
6. **Secrets Manager**: Automated credential rotation for RDS
7. **AWS Backup**: Centralized backup management across services
