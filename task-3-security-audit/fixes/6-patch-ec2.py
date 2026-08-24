#!/usr/bin/env python3
"""
Finding 6: Patch EC2 Instances with Critical CVEs

This script uses AWS Systems Manager Run Command to patch EC2 instances
with critical kernel and OpenSSL vulnerabilities.

Severity: CRITICAL (9.4 CVSS)
CVEs: 14 critical vulnerabilities in kernel and OpenSSL

Security features (following secure-python guidelines):
- No hardcoded credentials (uses boto3 default credential chain)
- Parameterized SSM commands (no command injection)
- Proper error handling (no sensitive data in error messages)
- Environment variable configuration
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
import boto3
from botocore.exceptions import ClientError, BotoCoreError

# Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Initialize boto3 clients
ssm_client = boto3.client('ssm', region_name=AWS_REGION)
ec2_client = boto3.client('ec2', region_name=AWS_REGION)


def get_instances_by_tag(tag_key, tag_value):
    """Find EC2 instances by tag using parameterized filters."""
    try:
        # Parameterized filters (no injection risk)
        response = ec2_client.describe_instances(
            Filters=[
                {'Name': f'tag:{tag_key}', 'Values': [tag_value]},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )

        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instances.append({
                    'id': instance['InstanceId'],
                    'name': next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'N/A'),
                    'type': instance['InstanceType'],
                    'state': instance['State']['Name']
                })

        return instances

    except (ClientError, BotoCoreError) as e:
        # Don't expose AWS credentials or internal details (CWE-209)
        print(f"ERROR: Failed to describe instances - {type(e).__name__}", file=sys.stderr)
        sys.exit(1)


def check_ssm_agent_status(instance_id):
    """Check if SSM agent is running and instance is managed."""
    try:
        response = ssm_client.describe_instance_information(
            Filters=[
                {'Key': 'InstanceIds', 'Values': [instance_id]}
            ]
        )

        if not response['InstanceInformationList']:
            return False, "SSM agent not running or instance not managed"

        info = response['InstanceInformationList'][0]
        if info['PingStatus'] != 'Online':
            return False, f"SSM agent offline (status: {info['PingStatus']})"

        return True, info

    except (ClientError, BotoCoreError) as e:
        print(f"WARNING: Could not check SSM status - {type(e).__name__}", file=sys.stderr)
        return False, "Unknown SSM status"


def get_current_package_versions(instance_id):
    """Get current kernel and OpenSSL versions."""
    print(f"→ Checking current package versions on {instance_id}...")

    try:
        # Run command to check versions
        # Using RunCommand with ShellScript document (secure as no user input in commands)
        response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunShellScript',
            Parameters={
                'commands': [
                    'uname -r',  # Kernel version
                    'openssl version',  # OpenSSL version
                    'dpkg -l | grep -E "linux-image|libssl" | awk \'{print $2, $3}\''  # Package versions
                ]
            },
            TimeoutSeconds=60
        )

        command_id = response['Command']['CommandId']

        # Wait for command to complete
        time.sleep(5)

        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )

        if output['Status'] == 'Success':
            print(f"✓ Current versions:\n{output['StandardOutputContent']}")
            return output['StandardOutputContent']
        else:
            print(f"⚠ Could not retrieve versions: {output['Status']}")
            return None

    except (ClientError, BotoCoreError) as e:
        print(f"WARNING: Version check failed - {type(e).__name__}", file=sys.stderr)
        return None


def run_patch_command(instance_id, verify_only=False):
    """
    Run apt-get update && apt-get upgrade on EC2 instance via SSM.

    Uses AWS-RunShellScript with non-interactive apt commands.
    No user input in commands (no command injection risk).
    """
    print(f"\n{'[VERIFY ONLY]' if verify_only else '[APPLYING PATCHES]'} Instance: {instance_id}")

    # Check SSM agent status first
    online, status = check_ssm_agent_status(instance_id)
    if not online:
        print(f"✗ Cannot patch: {status}")
        return False

    # Get current versions
    get_current_package_versions(instance_id)

    if verify_only:
        print("✓ Verification complete (no changes made)")
        return True

    if DRY_RUN:
        print("[DRY RUN] Would execute patching commands")
        return True

    # Patching commands (non-interactive, safe)
    patch_commands = [
        '#!/bin/bash',
        'set -euo pipefail',  # Exit on error
        'echo "Starting system update..."',

        # Update package lists
        'DEBIAN_FRONTEND=noninteractive apt-get update -y',

        # Upgrade packages (non-interactive, auto-accept)
        'DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"',

        # Specifically upgrade kernel and OpenSSL
        'DEBIAN_FRONTEND=noninteractive apt-get install -y linux-image-generic libssl3',

        # Clean up
        'apt-get autoremove -y',
        'apt-get autoclean',

        # Report new versions
        'echo "--- Post-Patch Versions ---"',
        'uname -r',
        'openssl version',

        # Check if reboot required
        'if [ -f /var/run/reboot-required ]; then echo "REBOOT_REQUIRED"; else echo "NO_REBOOT_NEEDED"; fi'
    ]

    try:
        print("→ Sending patch command to instance...")

        response = ssm_client.send_command(
            InstanceIds=[instance_id],
            DocumentName='AWS-RunShellScript',
            Parameters={
                'commands': patch_commands
            },
            TimeoutSeconds=600,  # 10 minutes for patching
            Comment=f'Patch CVEs - Finding 6 remediation - {datetime.now().isoformat()}'
        )

        command_id = response['Command']['CommandId']
        print(f"✓ Command sent (ID: {command_id})")

        # Wait for command to complete
        print("→ Waiting for patching to complete...")
        max_wait = 600  # 10 minutes
        waited = 0

        while waited < max_wait:
            time.sleep(10)
            waited += 10

            try:
                output = ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )

                status = output['Status']

                if status in ['Success', 'Failed', 'Cancelled', 'TimedOut']:
                    break

                print(f"  Status: {status} ({waited}s elapsed)")

            except ssm_client.exceptions.InvocationDoesNotExist:
                print(f"  Waiting for invocation... ({waited}s)")
                continue

        # Get final output
        output = ssm_client.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )

        if output['Status'] == 'Success':
            print(f"\n✓ Patching completed successfully")
            print(f"\nOutput:\n{output['StandardOutputContent']}")

            # Check if reboot required
            if 'REBOOT_REQUIRED' in output['StandardOutputContent']:
                print("\n⚠ REBOOT REQUIRED to apply kernel updates")
                print("  Run: aws ec2 reboot-instances --instance-ids " + instance_id)
            else:
                print("\n✓ No reboot required")

            return True

        else:
            print(f"\n✗ Patching failed with status: {output['Status']}")
            print(f"Error output:\n{output.get('StandardErrorContent', 'N/A')}")
            return False

    except (ClientError, BotoCoreError) as e:
        # Don't expose sensitive details (CWE-209)
        print(f"ERROR: Patching command failed - {type(e).__name__}", file=sys.stderr)
        return False


def reboot_instance(instance_id):
    """Reboot EC2 instance to apply kernel updates."""
    print(f"\n→ Rebooting instance {instance_id}...")

    if DRY_RUN:
        print("[DRY RUN] Would reboot instance")
        return True

    try:
        ec2_client.reboot_instances(InstanceIds=[instance_id])
        print(f"✓ Reboot initiated")

        # Wait for instance to be running again
        print("→ Waiting for instance to restart...")
        waiter = ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])

        # Wait for SSM agent to come back online
        print("→ Waiting for SSM agent to come online...")
        max_wait = 300  # 5 minutes
        waited = 0

        while waited < max_wait:
            time.sleep(10)
            waited += 10

            online, status = check_ssm_agent_status(instance_id)
            if online:
                print(f"✓ Instance back online after {waited}s")
                return True

            print(f"  Waiting for SSM agent... ({waited}s)")

        print(f"⚠ SSM agent did not come online within {max_wait}s")
        return False

    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: Reboot failed - {type(e).__name__}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Patch EC2 instances with critical CVEs using AWS Systems Manager'
    )
    parser.add_argument('--instance-id', help='Specific instance ID to patch')
    parser.add_argument('--tag-key', default='Project', help='Tag key to filter instances')
    parser.add_argument('--tag-value', default='NimbusTech', help='Tag value to filter instances')
    parser.add_argument('--verify-only', action='store_true', help='Check versions without patching')
    parser.add_argument('--reboot', action='store_true', help='Reboot after patching')

    args = parser.parse_args()

    print("EC2 Patching Script - Finding 6 Remediation")
    print(f"Region: {AWS_REGION}")
    print(f"Dry Run: {DRY_RUN}")
    print("-" * 60)

    # Get instances to patch
    if args.instance_id:
        instances = [{'id': args.instance_id, 'name': 'Specified', 'type': 'N/A', 'state': 'running'}]
    else:
        print(f"→ Finding instances with tag {args.tag_key}={args.tag_value}...")
        instances = get_instances_by_tag(args.tag_key, args.tag_value)

    if not instances:
        print("No instances found to patch")
        return 0

    print(f"\nFound {len(instances)} instance(s) to patch:")
    for inst in instances:
        print(f"  - {inst['id']} ({inst['name']}) - {inst['type']}")

    # Patch each instance
    results = []
    for inst in instances:
        success = run_patch_command(inst['id'], verify_only=args.verify_only)
        results.append((inst['id'], success))

        # Reboot if requested and not verify-only
        if success and args.reboot and not args.verify_only:
            reboot_instance(inst['id'])

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    for instance_id, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {instance_id}")

    failed = sum(1 for _, success in results if not success)
    if failed > 0:
        print(f"\n⚠ {failed} instance(s) failed to patch")
        return 1
    else:
        print(f"\n✓ All instances patched successfully")
        return 0


if __name__ == '__main__':
    sys.exit(main())
