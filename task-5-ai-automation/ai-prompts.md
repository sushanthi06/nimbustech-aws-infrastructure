# AI-Assisted Automation: Prompts & Analysis

## Task Chosen

**Option (C):** Write a Terraform module for a reusable 'secure-ec2' pattern
- EC2 in private subnet
- SSM access only (no SSH)
- CloudWatch agent pre-configured
- IMDSv2 enforced

---

## Prompt #1: Initial Module Structure

**Prompt to AI:**
```
Create a Terraform module for a "secure-ec2" pattern with these requirements:
- EC2 instance in a private subnet (no public IP)
- SSM access only, no SSH port 22
- CloudWatch agent pre-configured via user-data
- IMDSv2 enforced for metadata access
- Include variables for instance_type, ami_id, subnet_id, vpc_id
- Include outputs for instance_id, private_ip
- Add proper IAM roles for SSM and CloudWatch
- Use security best practices
```

**AI Response (Claude):**

The AI generated a complete Terraform module with:
1. Main `main.tf` with instance resource
2. IAM role and policies for SSM
3. Security group with no SSH ingress
4. User-data script for CloudWatch agent
5. Variables and outputs

---

## Prompt #2: Add CloudWatch Agent Configuration

**Prompt to AI:**
```
Enhance the user-data script to install and configure the CloudWatch agent.
The agent should collect:
- Memory utilization (mem_used_percent)
- Disk utilization (disk_used_percent)
- CPU utilization (from CloudWatch metrics)
- Application logs from /var/log/app/*.log

Use a JSON configuration file for the agent.
Ensure the installation is idempotent and handles errors.
```

**AI Response:**

The AI provided a bash script with:
- CloudWatch agent installation from AWS URL
- JSON configuration for metrics and logs
- Error handling with `set -euo pipefail`
- Service startup commands

---

## Prompt #3: IMDSv2 Configuration

**Prompt to AI:**
```
Add Terraform configuration to enforce IMDSv2 on the EC2 instance.
Explain what IMDSv2 is and why it's more secure than IMDSv1.
Include the specific Terraform block needed.
```

**AI Response:**

```hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"  # IMDSv2 only
  http_put_response_hop_limit = 1
  instance_metadata_tags      = "enabled"
}
```

**Explanation provided:**
- IMDSv1: Simple HTTP GET to 169.254.169.254 (vulnerable to SSRF)
- IMDSv2: Requires session token via PUT request first (prevents SSRF)
- `http_tokens = "required"` enforces IMDSv2 only

---

## Prompt #4: Security Group Hardening

**Prompt to AI:**
```
Review the security group configuration.
The instance is in a private subnet and should:
- Only allow outbound HTTPS (443) for AWS API calls
- Only allow outbound HTTP (80) for package managers
- No SSH ingress (SSM only)
- Document why each rule exists

Add comments explaining the security rationale.
```

**AI Response:**

Enhanced security group with:
- Documented egress rules
- No ingress rules (SSM via AWS PrivateLink doesn't need SG rules)
- Comments explaining CWE prevention
- Note about VPC endpoints reducing egress needs

---

## Prompt #5: Make Module Reusable

**Prompt to AI:**
```
Make this module reusable for different environments (dev/staging/prod).
Add variables for:
- Environment name (for tagging)
- Monitoring interval for CloudWatch agent (60s for prod, 300s for dev)
- Log retention days
- Enable detailed monitoring (boolean)

Add validation for variables where appropriate.
```

**AI Response:**

Added:
- `environment` variable with validation
- `monitoring_interval` variable with default 60
- `log_retention_days` variable with validation (1-3653 days)
- `enable_detailed_monitoring` boolean
- Variable validation blocks

---

## What the AI Got Right ✅

1. **Security Defaults:**
   - Correctly enforced IMDSv2
   - No SSH ingress by default
   - Proper IAM least privilege (SSM + CloudWatch policies)
   - Used managed AWS policies instead of custom (simpler, maintained by AWS)

2. **Terraform Best Practices:**
   - Proper use of `depends_on` for IAM role propagation
   - Output values for integration with other modules
   - Variable validation constraints
   - Sensible defaults (60s monitoring, t3.micro default instance)

3. **CloudWatch Agent Configuration:**
   - JSON structure was correct
   - Used namespaced metrics (prevents collision)
   - Included both metrics and logs collection
   - Proper log group naming convention

4. **User-Data Script:**
   - Used `set -euo pipefail` for safety
   - Checked for errors during installation
   - Made script idempotent (can run multiple times)

5. **Documentation:**
   - Clear variable descriptions
   - Examples of usage
   - Security rationale in comments

---

## What the AI Got Wrong / Needed Fixing ❌

### 1. **User-Data Encoding**

**AI Output:**
```hcl
user_data = file("${path.module}/user-data.sh")
```

**Problem:** Should be base64-encoded for Terraform

**Fix:**
```hcl
user_data = base64encode(templatefile("${path.module}/user-data.sh", {
  cloudwatch_config = jsonencode(local.cloudwatch_config)
}))
```

**Why:** Terraform's `file()` doesn't handle templating. Use `templatefile()` + `base64encode()`.

---

### 2. **CloudWatch Agent Configuration Path**

**AI Output:**
User-data script wrote config to `/opt/aws/amazon-cloudwatch-agent/etc/config.json`

**Problem:** Hardcoded values in bash, should be templated from Terraform

**Fix:**
Pass CloudWatch config as Terraform variable → template into user-data

**Why:** Makes config customizable per environment without editing bash script

---

### 3. **IAM Policy Attachment Timing**

**AI Output:**
```hcl
resource "aws_instance" "main" {
  iam_instance_profile = aws_iam_instance_profile.ssm.name
  # ... no depends_on
}
```

**Problem:** IAM roles take time to propagate. Instance might start before role is ready.

**Fix:**
```hcl
resource "aws_instance" "main" {
  iam_instance_profile = aws_iam_instance_profile.ssm.name

  depends_on = [
    aws_iam_role_policy_attachment.ssm,
    aws_iam_role_policy_attachment.cloudwatch
  ]
}
```

**Why:** Prevents "Instance has insufficient permissions" errors on first boot

---

### 4. **Security Group Egress Too Permissive**

**AI Output:**
```hcl
egress {
  from_port   = 0
  to_port     = 0
  protocol    = "-1"  # All traffic
  cidr_blocks = ["0.0.0.0/0"]
}
```

**Problem:** Allows ALL outbound traffic (not least privilege)

**Fix:**
```hcl
# Only HTTPS for AWS APIs
egress {
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  description = "HTTPS for AWS API calls (SSM, CloudWatch)"
}

# HTTP for package managers (apt, yum)
egress {
  from_port   = 80
  to_port     = 80
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
  description = "HTTP for package manager mirrors"
}
```

**Why:** Least privilege - only allow what's actually needed

---

### 5. **Missing VPC Endpoint Recommendation**

**AI Output:** No mention of VPC endpoints

**Problem:** Module assumes internet access via NAT Gateway (costs money)

**Fix:** Added documentation about using VPC endpoints to reduce NAT costs:
```hcl
# Optional: Use VPC endpoints to avoid NAT Gateway costs
# - com.amazonaws.REGION.ssm
# - com.amazonaws.REGION.ssmmessages
# - com.amazonaws.REGION.ec2messages
# - com.amazonaws.REGION.monitoring
# - com.amazonaws.REGION.logs
```

**Why:** VPC endpoints are free (except interface endpoints), reduce NAT data transfer

---

### 6. **CloudWatch Agent Installation URL**

**AI Output:**
```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
```

**Problem:** Hardcoded to `ubuntu`, doesn't work for Amazon Linux

**Fix:**
Add variable for OS type and template the URL:
```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/${os_type}/amd64/latest/amazon-cloudwatch-agent.deb
```

**Why:** Module should work with multiple Linux distributions

---

### 7. **No Terratest / Validation**

**AI Output:** Just the Terraform code, no tests

**Problem:** No way to verify the module works

**Fix:** Added example usage + manual testing steps in README

**Ideal:** Would add Terratest Go tests, but out of scope for this exercise

---

## Iterative Improvements Made

### Iteration 1: Initial Generation
- ✅ Basic structure
- ✅ IAM roles
- ❌ User-data not templated
- ❌ Security group too permissive

### Iteration 2: Security Hardening
- ✅ Fixed security group egress
- ✅ Added IMDSv2 enforcement
- ❌ Still missing VPC endpoint docs

### Iteration 3: Configurability
- ✅ Added environment variables
- ✅ Templated CloudWatch config
- ✅ Added validation constraints

### Iteration 4: Documentation
- ✅ Added usage examples
- ✅ Explained security decisions
- ✅ Documented VPC endpoint integration

---

## Key Lessons Learned

### 1. **AI is Great for Boilerplate**
   - Terraform resource structure: 95% correct
   - IAM policy JSON: 100% correct
   - Basic bash scripts: 90% correct

### 2. **AI Needs Security Review**
   - Default to "allow all egress" (common pattern, but not secure)
   - Doesn't always think about least privilege
   - **Human must review all security-critical code**

### 3. **AI Doesn't Know Your Environment**
   - Suggested hardcoded Ubuntu URLs
   - Didn't know our VPC has endpoints
   - Needs context about infrastructure

### 4. **Iterative Prompting Works Best**
   - Start broad ("create a module")
   - Then refine ("add CloudWatch")
   - Then harden ("review security")
   - Each iteration improves quality

### 5. **Validation is Critical**
   - AI doesn't test its own code
   - Assumed certain AWS behaviors (IAM propagation) that can fail
   - **Always test in staging before prod**

---

## Time Savings Estimate

| Task | Manual Time | AI-Assisted Time | Savings |
|------|-------------|------------------|---------|
| Module structure | 30 min | 5 min | 25 min |
| IAM roles/policies | 20 min | 2 min | 18 min |
| Security group | 15 min | 3 min | 12 min |
| User-data script | 45 min | 10 min | 35 min |
| CloudWatch config | 30 min | 5 min | 25 min |
| Documentation | 40 min | 10 min | 30 min |
| **Total** | **3 hours** | **35 minutes** | **2.5 hours** |

**Time savings: 75%**

**However:** Includes 15 minutes of prompt engineering and 10 minutes of security review not in original estimate.

**Net time savings: ~65%**

---

## Prompts That Didn't Work Well

### ❌ Prompt: "Make this production-ready"
**Problem:** Too vague. AI added logging, tags, but didn't address real prod concerns (HA, scaling, monitoring)

**Better:** "Add these production features: [specific list]"

---

### ❌ Prompt: "Optimize this code"
**Problem:** AI made it "clever" with complex conditionals and dynamic blocks

**Better:** "Make this code simple and readable"

---

### ❌ Prompt: "Fix security issues"
**Problem:** AI didn't find any (even though egress was too broad)

**Better:** "Review egress rules against least-privilege principle"

---

## Recommendations for Using AI Tools

1. **Be Specific:** Vague prompts → generic code
2. **Iterate:** Don't expect perfection in one shot
3. **Review Security:** AI doesn't understand threat models
4. **Test Everything:** AI-generated code can look right but fail at runtime
5. **Use AI for Patterns:** Terraform modules, IAM policies, common scripts
6. **Don't Use AI for:** Architecture decisions, compliance requirements, novel solutions

---

## Final Assessment

**What AI is Good At:**
- ✅ Boilerplate code generation
- ✅ Terraform/CloudFormation syntax
- ✅ Common security patterns (IAM, SSH → SSM)
- ✅ Documentation templates
- ✅ Bash scripting

**What AI Struggles With:**
- ❌ Least-privilege security (defaults to permissive)
- ❌ Environment-specific context
- ❌ Testing and validation
- ❌ Nuanced architectural decisions
- ❌ Cost optimization tradeoffs

**Overall:**
AI saved ~2.5 hours on this task, but required:
- Clear, specific prompts
- Multiple iterations
- Security review by human
- Testing and validation

**Would I use AI for this again?** Absolutely. The time savings are real, but **AI is a tool, not a replacement for engineering judgment.**
