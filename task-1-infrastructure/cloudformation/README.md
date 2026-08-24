# CloudFormation Deployment Guide

## Overview

This folder contains CloudFormation templates for deploying NimbusTech's secure AWS infrastructure. The templates are organized as separate stacks for modularity and easier management.

## Architecture

```
vpc.yaml               → VPC, subnets, NAT, IGW, Flow Logs
security-groups.yaml   → ALB, App, and RDS security groups
rds.yaml              → PostgreSQL Multi-AZ database
alb.yaml              → Application Load Balancer + Target Group
ec2.yaml              → EC2 instances with SSM access
```

## Prerequisites

1. AWS CLI installed and configured
2. AWS account with appropriate permissions
3. Database password ready (min 8 characters)

## Deployment Order

Deploy in this order (each stack depends on outputs from previous):

### 1. VPC Stack

```bash
aws cloudformation create-stack \
  --stack-name nimbustech-vpc \
  --template-body file://vpc.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=nimbustech \
    ParameterKey=Environment,ParameterValue=production \
  --capabilities CAPABILITY_IAM
```

**Wait for completion:**
```bash
aws cloudformation wait stack-create-complete --stack-name nimbustech-vpc
```

### 2. Security Groups Stack

```bash
# Get VPC ID from previous stack
VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`VPCId`].OutputValue' \
  --output text)

aws cloudformation create-stack \
  --stack-name nimbustech-security-groups \
  --template-body file://security-groups.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=nimbustech \
    ParameterKey=VPCId,ParameterValue=$VPC_ID
```

**Wait:**
```bash
aws cloudformation wait stack-create-complete --stack-name nimbustech-security-groups
```

### 3. RDS Stack

```bash
# Get subnet and security group IDs
DB_SUBNET1=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PrivateDBSubnet1Id`].OutputValue' \
  --output text)

DB_SUBNET2=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PrivateDBSubnet2Id`].OutputValue' \
  --output text)

RDS_SG=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-security-groups \
  --query 'Stacks[0].Outputs[?OutputKey==`RDSSecurityGroupId`].OutputValue' \
  --output text)

# Deploy RDS (provide your password)
aws cloudformation create-stack \
  --stack-name nimbustech-rds \
  --template-body file://rds.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=nimbustech \
    ParameterKey=DBName,ParameterValue=nimbustechdb \
    ParameterKey=DBUsername,ParameterValue=nimbusadmin \
    ParameterKey=DBPassword,ParameterValue=YOUR_SECURE_PASSWORD_HERE \
    ParameterKey=DBInstanceClass,ParameterValue=db.t3.medium \
    ParameterKey=MultiAZ,ParameterValue=true \
    ParameterKey=PrivateDBSubnet1,ParameterValue=$DB_SUBNET1 \
    ParameterKey=PrivateDBSubnet2,ParameterValue=$DB_SUBNET2 \
    ParameterKey=RDSSecurityGroup,ParameterValue=$RDS_SG \
  --capabilities CAPABILITY_IAM
```

**Wait (this takes ~10 minutes):**
```bash
aws cloudformation wait stack-create-complete --stack-name nimbustech-rds
```

### 4. ALB Stack

```bash
# Get public subnets and ALB security group
PUB_SUBNET1=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicSubnet1Id`].OutputValue' \
  --output text)

PUB_SUBNET2=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PublicSubnet2Id`].OutputValue' \
  --output text)

ALB_SG=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-security-groups \
  --query 'Stacks[0].Outputs[?OutputKey==`ALBSecurityGroupId`].OutputValue' \
  --output text)

aws cloudformation create-stack \
  --stack-name nimbustech-alb \
  --template-body file://alb.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=nimbustech \
    ParameterKey=PublicSubnet1,ParameterValue=$PUB_SUBNET1 \
    ParameterKey=PublicSubnet2,ParameterValue=$PUB_SUBNET2 \
    ParameterKey=ALBSecurityGroup,ParameterValue=$ALB_SG \
    ParameterKey=VPCId,ParameterValue=$VPC_ID
```

**Wait:**
```bash
aws cloudformation wait stack-create-complete --stack-name nimbustech-alb
```

### 5. EC2 Stack

```bash
# Get all required parameters
PRIV_APP_SUBNET1=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PrivateAppSubnet1Id`].OutputValue' \
  --output text)

PRIV_APP_SUBNET2=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-vpc \
  --query 'Stacks[0].Outputs[?OutputKey==`PrivateAppSubnet2Id`].OutputValue' \
  --output text)

APP_SG=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-security-groups \
  --query 'Stacks[0].Outputs[?OutputKey==`AppSecurityGroupId`].OutputValue' \
  --output text)

TG_ARN=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-alb \
  --query 'Stacks[0].Outputs[?OutputKey==`TargetGroupArn`].OutputValue' \
  --output text)

DB_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-rds \
  --query 'Stacks[0].Outputs[?OutputKey==`DBEndpoint`].OutputValue' \
  --output text)

DB_PORT=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-rds \
  --query 'Stacks[0].Outputs[?OutputKey==`DBPort`].OutputValue' \
  --output text)

aws cloudformation create-stack \
  --stack-name nimbustech-ec2 \
  --template-body file://ec2.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=nimbustech \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
    ParameterKey=PrivateAppSubnet1,ParameterValue=$PRIV_APP_SUBNET1 \
    ParameterKey=PrivateAppSubnet2,ParameterValue=$PRIV_APP_SUBNET2 \
    ParameterKey=AppSecurityGroup,ParameterValue=$APP_SG \
    ParameterKey=TargetGroupArn,ParameterValue=$TG_ARN \
    ParameterKey=DBEndpoint,ParameterValue=$DB_ENDPOINT \
    ParameterKey=DBPort,ParameterValue=$DB_PORT \
    ParameterKey=DBName,ParameterValue=nimbustechdb \
  --capabilities CAPABILITY_NAMED_IAM
```

**Wait:**
```bash
aws cloudformation wait stack-create-complete --stack-name nimbustech-ec2
```

## Verify Deployment

### 1. Get Application URL

```bash
aws cloudformation describe-stacks \
  --stack-name nimbustech-alb \
  --query 'Stacks[0].Outputs[?OutputKey==`ApplicationURL`].OutputValue' \
  --output text
```

### 2. Test ALB Health

```bash
ALB_URL=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-alb \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNSName`].OutputValue' \
  --output text)

curl http://$ALB_URL/health
```

### 3. Connect to EC2 via SSM

```bash
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`Instance1Id`].OutputValue' \
  --output text)

aws ssm start-session --target $INSTANCE_ID
```

### 4. Verify RDS Connectivity (from EC2)

```bash
# On EC2 instance via SSM
DB_HOST=$(aws cloudformation describe-stacks \
  --stack-name nimbustech-rds \
  --query 'Stacks[0].Outputs[?OutputKey==`DBEndpoint`].OutputValue' \
  --output text)

telnet $DB_HOST 5432
```

## Update Stacks

To update a stack:

```bash
aws cloudformation update-stack \
  --stack-name nimbustech-vpc \
  --template-body file://vpc.yaml \
  --parameters ParameterKey=ProjectName,ParameterValue=nimbustech
```

## Delete Stacks

Delete in reverse order:

```bash
# 1. EC2
aws cloudformation delete-stack --stack-name nimbustech-ec2
aws cloudformation wait stack-delete-complete --stack-name nimbustech-ec2

# 2. ALB
aws cloudformation delete-stack --stack-name nimbustech-alb
aws cloudformation wait stack-delete-complete --stack-name nimbustech-alb

# 3. RDS (creates final snapshot)
aws cloudformation delete-stack --stack-name nimbustech-rds
aws cloudformation wait stack-delete-complete --stack-name nimbustech-rds

# 4. Security Groups
aws cloudformation delete-stack --stack-name nimbustech-security-groups
aws cloudformation wait stack-delete-complete --stack-name nimbustech-security-groups

# 5. VPC
aws cloudformation delete-stack --stack-name nimbustech-vpc
aws cloudformation wait stack-delete-complete --stack-name nimbustech-vpc
```

## Quick Deployment Script

Save this as `deploy-all.sh`:

```bash
#!/bin/bash
set -e

PROJECT_NAME="nimbustech"
DB_PASSWORD="YOUR_SECURE_PASSWORD"

echo "=== Deploying VPC ==="
aws cloudformation create-stack \
  --stack-name ${PROJECT_NAME}-vpc \
  --template-body file://vpc.yaml \
  --parameters ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME \
  --capabilities CAPABILITY_IAM

aws cloudformation wait stack-create-complete --stack-name ${PROJECT_NAME}-vpc

echo "=== Deploying Security Groups ==="
VPC_ID=$(aws cloudformation describe-stacks --stack-name ${PROJECT_NAME}-vpc --query 'Stacks[0].Outputs[?OutputKey==`VPCId`].OutputValue' --output text)

aws cloudformation create-stack \
  --stack-name ${PROJECT_NAME}-security-groups \
  --template-body file://security-groups.yaml \
  --parameters ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME ParameterKey=VPCId,ParameterValue=$VPC_ID

aws cloudformation wait stack-create-complete --stack-name ${PROJECT_NAME}-security-groups

echo "=== Deploying RDS (this takes ~10 minutes) ==="
# ... (add remaining stacks)

echo "=== Deployment Complete ==="
```

## Estimated Costs

Based on CloudFormation deployment:

| Resource | Monthly Cost |
|----------|--------------|
| 2x EC2 t3.medium | $60.74 |
| RDS db.t3.medium Multi-AZ | $98.40 |
| NAT Gateway | $32.00 + data |
| ALB | $16.20 |
| CloudWatch | $10.00 |
| **Total** | **~$217/month** |

## Troubleshooting

### Stack Creation Failed

View failure reason:
```bash
aws cloudformation describe-stack-events \
  --stack-name nimbustech-vpc \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'
```

### RDS Creation Timeout

RDS takes 10-15 minutes. If it times out, it's likely still creating. Check:
```bash
aws rds describe-db-instances --db-instance-identifier nimbustech-db
```

### EC2 Instances Not Healthy in Target Group

Check:
1. Security group allows ALB → EC2 on port 3000
2. Application is listening on 0.0.0.0:3000 (not 127.0.0.1)
3. /health endpoint returns 200

```bash
aws elbv2 describe-target-health --target-group-arn $TG_ARN
```

## Next Steps

1. Deploy application code to EC2 instances
2. Set up Route 53 domain
3. Request ACM certificate for HTTPS
4. Enable CloudTrail (see Task 3)
5. Set up billing alarms (see Task 4)
