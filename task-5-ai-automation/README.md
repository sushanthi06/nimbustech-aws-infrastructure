# Task 5: AI-Assisted Automation

## Overview

This task demonstrates transparent use of AI tools (Claude) to create a reusable CloudFormation template for secure EC2 instances. The template implements security best practices: SSM-only access, IMDSv2, CloudWatch monitoring, and least-privilege security groups.

## Task Chosen

**Option (C):** CloudFormation template for 'secure-ec2' pattern
- EC2 in private subnet
- SSM access only (no SSH)
- CloudWatch agent pre-configured
- IMDSv2 enforced

## Files

- `ai-prompts.md` - Complete prompt history, AI outputs, and analysis
- `script/secure-ec2.yaml` - CloudFormation template (AI-generated + human-reviewed)
- `README.md` - This file

## How AI Was Used

### Prompt Engineering Process

1. **Initial Structure** - Asked AI to create basic CloudFormation template
2. **CloudWatch Integration** - Added metrics and log collection
3. **IMDSv2 Enforcement** - Enhanced metadata security
4. **Security Hardening** - Reviewed and fixed security group rules
5. **Reusability** - Added parameters and validation

**Total prompts:** 5  
**Iterations:** 4  
**Time saved:** ~2.5 hours (65% reduction)

See `ai-prompts.md` for complete prompt history and analysis.

## What AI Got Right ✅

1. **Security Defaults**
   - Correctly enforced IMDSv2 (`HttpTokens: required`)
   - No SSH ingress by default
   - Proper IAM least privilege (AWS managed policies)
   - EBS encryption enabled

2. **CloudFormation Best Practices**
   - Outputs for stack integration
   - Parameter validation constraints
   - Sensible defaults (t3.micro, 60s monitoring)
   - Proper use of `!Sub` and `!Ref` functions

3. **CloudWatch Agent Configuration**
   - JSON structure correct
   - Namespaced metrics prevent collision
   - Both metrics and logs collection
   - Proper log group naming

4. **User-Data Script**
   - Used `set -euo pipefail` for safety
   - Error checking during installation
   - Idempotent (can run multiple times)

## What AI Got Wrong ❌

### 1. Security Group Egress Too Permissive

**AI Output:**
```yaml
SecurityGroupEgress:
  - IpProtocol: -1  # All traffic
    CidrIp: 0.0.0.0/0
```

**Problem:** Allows ALL outbound traffic (not least privilege)

**Fixed:** Only allow HTTPS (443) and HTTP (80) - see `secure-ec2.yaml`

### 2. Missing IAM Role Dependency

**AI Output:** No explicit dependency between Instance and InstanceProfile

**Problem:** CloudFormation might try to create instance before IAM role is ready

**Fixed:** Added `DependsOn: InstanceProfile` (though CloudFormation handles this implicitly via Ref)

### 3. No Parameter Validation

**AI Output:** Basic parameter types only

**Fixed:** Added `AllowedValues` constraints for Environment, InstanceType, MonitoringInterval

### 4. Missing VPC Endpoint Recommendation

**AI Output:** No mention of VPC endpoints

**Problem:** Assumes internet access via NAT Gateway (costs money)

**Fixed:** Added documentation about VPC endpoints to reduce NAT costs

## Usage Example

```bash
# Deploy the secure EC2 instance
aws cloudformation create-stack \
  --stack-name my-app-server \
  --template-body file://secure-ec2.yaml \
  --parameters \
    ParameterKey=ProjectName,ParameterValue=myproject \
    ParameterKey=Environment,ParameterValue=prod \
    ParameterKey=VPCId,ParameterValue=vpc-12345678 \
    ParameterKey=SubnetId,ParameterValue=subnet-abcd1234 \
    ParameterKey=InstanceType,ParameterValue=t3.medium \
    ParameterKey=MonitoringInterval,ParameterValue=60 \
    ParameterKey=LogRetentionDays,ParameterValue=30 \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for completion
aws cloudformation wait stack-create-complete --stack-name my-app-server

# Get instance ID
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name my-app-server \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text)

# Connect via SSM
aws ssm start-session --target $INSTANCE_ID
```

## Testing the Template

### 1. Validate Template

```bash
aws cloudformation validate-template --template-body file://secure-ec2.yaml
```

### 2. Deploy to Staging

```bash
aws cloudformation create-stack \
  --stack-name test-secure-ec2 \
  --template-body file://secure-ec2.yaml \
  --parameters file://test-parameters.json \
  --capabilities CAPABILITY_NAMED_IAM
```

### 3. Verify Security

```bash
# Check IMDSv2 enforcement
aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].MetadataOptions'

# Expected: HttpTokens: required

# Check no SSH ingress
SG_ID=$(aws cloudformation describe-stacks \
  --stack-name test-secure-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`SecurityGroupId`].OutputValue' \
  --output text)

aws ec2 describe-security-groups \
  --group-ids $SG_ID \
  --query 'SecurityGroups[0].IpPermissions[?ToPort==`22`]'

# Expected: []
```

### 4. Verify CloudWatch

```bash
# Check metrics
aws cloudwatch get-metric-statistics \
  --namespace "myproject/prod" \
  --metric-name MemoryUtilization \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average

# Check logs
LOG_GROUP=$(aws cloudformation describe-stacks \
  --stack-name test-secure-ec2 \
  --query 'Stacks[0].Outputs[?OutputKey==`LogGroupName`].OutputValue' \
  --output text)

aws logs tail $LOG_GROUP --follow
```

## Security Features

✅ **No SSH** - Use SSM Session Manager (no port 22 ingress)  
✅ **IMDSv2** - Prevents SSRF attacks on instance metadata  
✅ **Least-Privilege SG** - Only HTTPS/HTTP egress, no ingress  
✅ **EBS Encryption** - Data at rest encryption enabled  
✅ **IAM Managed Policies** - AWS-maintained, regularly updated  
✅ **CloudWatch Logging** - Centralized log management  
✅ **Configurable Monitoring** - 60s, 300s, or 600s intervals  

## Cost Optimization

- **Default instance:** t3.micro ($7.50/month)
- **CloudWatch Logs:** ~$0.50/month (depends on log volume)
- **CloudWatch Metrics:** Free (basic)
- **SSM:** Free
- **Total:** ~$8/month per instance

**Optional:** Use VPC endpoints to reduce NAT Gateway costs:
- `com.amazonaws.REGION.ssm`
- `com.amazonaws.REGION.ssmmessages`
- `com.amazonaws.REGION.ec2messages`
- `com.amazonaws.REGION.logs`

## Key Learnings

### AI Strengths
- ✅ Boilerplate code generation (95% correct)
- ✅ CloudFormation syntax and structure
- ✅ Common security patterns
- ✅ Documentation templates

### AI Weaknesses
- ❌ Least-privilege security (defaults to permissive)
- ❌ Environment-specific context
- ❌ Testing and validation
- ❌ Cost optimization tradeoffs

### Best Practices for AI-Assisted Development

1. **Be Specific** - Vague prompts → generic code
2. **Iterate** - Don't expect perfection first try
3. **Review Security** - AI doesn't understand threat models
4. **Test Everything** - AI code can look right but fail at runtime
5. **Document Changes** - Track what AI generated vs what you fixed

## Time Analysis

| Task | Manual | AI-Assisted | Savings |
|------|--------|-------------|---------|
| Template structure | 30 min | 5 min | 25 min |
| IAM roles/policies | 20 min | 2 min | 18 min |
| Security group | 15 min | 3 min | 12 min |
| User-data script | 45 min | 10 min | 35 min |
| CloudWatch config | 30 min | 5 min | 25 min |
| Documentation | 40 min | 10 min | 30 min |
| **Total** | **3 hours** | **35 min** | **145 min** |

**Net time savings: 65%** (includes prompt engineering and security review)

## CloudFormation vs Terraform

**Why CloudFormation for this exercise:**

✅ **Native AWS Integration** - No external tools needed  
✅ **StackSets** - Deploy across multiple accounts/regions  
✅ **Change Sets** - Preview changes before applying  
✅ **Drift Detection** - Find manual changes  
✅ **Free** - No state file management needed  

**Learning Resources:**
- [CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-reference.html)
- [Intrinsic Functions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference.html)
- [Best Practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)

## Conclusion

AI tools are excellent for:
- Generating boilerplate infrastructure code
- Providing syntax examples
- Creating documentation templates
- Speeding up development

**However**, AI-generated code MUST be:
- ✅ Security reviewed by humans
- ✅ Tested in staging before production
- ✅ Adapted to your specific environment
- ✅ Validated against compliance requirements

**Would I use AI for this again?** Absolutely. The time savings are real, but AI is a **tool to augment engineering judgment**, not replace it.
