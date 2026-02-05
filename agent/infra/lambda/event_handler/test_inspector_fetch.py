#!/usr/bin/env python3
"""
测试 Inspector API 漏洞抓取逻辑

用法:
    python test_inspector_fetch.py

测试目标:
    auth-platform-production/user-service:sha256:4d8d0d9db1c4c929f729ae86e6c863a60d3ba149e7ce7b3d87a46a85581db64b
"""

import json
import boto3
from typing import Optional

# 配置
REPO_NAME = "auth-platform-production/user-service"
IMAGE_DIGEST = "sha256:4d8d0d9db1c4c929f729ae86e6c863a60d3ba149e7ce7b3d87a46a85581db64b"
IMAGE_TAG = "latest"  # 可选，用于显示
REGISTRY_ID = ""  # 留空，使用默认账户

# 创建 Inspector2 客户端 (指定区域)
REGION = "ap-northeast-1"  # 根据实际情况修改
inspector_client = boto3.client('inspector2', region_name=REGION)


def extract_vulnerability_from_inspector_finding(finding: dict) -> Optional[dict]:
    """从 Inspector Finding 提取漏洞信息。"""
    try:
        # 提取 CVE ID
        vulnerability_id = finding.get('packageVulnerabilityDetails', {}).get('vulnerabilityId', '')
        if not vulnerability_id:
            vulnerability_id = finding.get('title', '')
        if not vulnerability_id:
            return None

        # 提取严重性
        severity = finding.get('severity', 'UNKNOWN')

        # 提取 CVSS 分数
        cvss_score = 0.0
        cvss_list = finding.get('packageVulnerabilityDetails', {}).get('cvss', [])
        for cvss in cvss_list:
            if cvss.get('version', '').startswith('3'):
                cvss_score = cvss.get('baseScore', 0.0)
                break
        if cvss_score == 0.0 and cvss_list:
            cvss_score = cvss_list[0].get('baseScore', 0.0)

        # 提取受影响的包信息
        vulnerable_packages = finding.get('packageVulnerabilityDetails', {}).get('vulnerablePackages', [])
        if not vulnerable_packages:
            package_name = 'Unknown'
            current_version = 'Unknown'
            fixed_version = 'Not available'
            package_manager = 'Unknown'
        else:
            package = vulnerable_packages[0]
            package_name = package.get('name', 'Unknown')
            current_version = package.get('version', 'Unknown')
            fixed_version = package.get('fixedInVersion', 'Not available')
            package_manager = package.get('packageManager', 'Unknown')

        # 检查是否有公开利用
        exploit_available = finding.get('exploitAvailable', 'NO') == 'YES'

        # 提取描述
        description = finding.get('description', '')

        return {
            'cve_id': vulnerability_id,
            'severity': severity,
            'cvss_score': cvss_score,
            'package_name': package_name,
            'current_version': current_version,
            'fixed_version': fixed_version,
            'package_manager': package_manager.lower(),
            'exploit_available': exploit_available,
            'description': description[:100] + '...' if len(description) > 100 else description
        }
    except Exception as e:
        print(f"Error extracting vulnerability: {e}")
        return None


def get_container_findings(repo_name: str, image_digest: str) -> list:
    """获取指定容器镜像的所有 HIGH/CRITICAL 漏洞。"""
    print(f"\n{'='*60}")
    print(f"Fetching Inspector findings for: {repo_name}")
    print(f"Image digest: {image_digest}")
    print(f"{'='*60}\n")

    vulnerabilities = []
    next_token = None

    # 构建筛选条件
    filter_criteria = {
        'ecrImageRepositoryName': [{'comparison': 'EQUALS', 'value': repo_name}],
        'ecrImageHash': [{'comparison': 'EQUALS', 'value': image_digest}],
        'severity': [
            {'comparison': 'EQUALS', 'value': 'CRITICAL'},
            {'comparison': 'EQUALS', 'value': 'HIGH'}
        ],
        'findingType': [{'comparison': 'EQUALS', 'value': 'PACKAGE_VULNERABILITY'}],
        'resourceType': [{'comparison': 'EQUALS', 'value': 'AWS_ECR_CONTAINER_IMAGE'}]
    }

    print(f"Filter criteria:")
    print(json.dumps(filter_criteria, indent=2))
    print()

    page_count = 0
    while True:
        page_count += 1
        params = {
            'filterCriteria': filter_criteria,
            'maxResults': 100
        }
        if next_token:
            params['nextToken'] = next_token

        response = inspector_client.list_findings(**params)

        findings_in_page = response.get('findings', [])
        print(f"Page {page_count}: Retrieved {len(findings_in_page)} findings")

        for finding in findings_in_page:
            vuln = extract_vulnerability_from_inspector_finding(finding)
            if vuln:
                vulnerabilities.append(vuln)

        next_token = response.get('nextToken')
        if not next_token:
            break

    return vulnerabilities


def aggregate_vulnerabilities(vulnerabilities: list) -> dict:
    """聚合漏洞信息，生成摘要。"""
    seen_cves = set()
    unique_vulns = []
    critical_count = 0
    high_count = 0
    packages_affected = set()
    package_managers = set()

    for vuln in vulnerabilities:
        cve_id = vuln.get('cve_id', '')
        if cve_id and cve_id not in seen_cves:
            seen_cves.add(cve_id)
            unique_vulns.append(vuln)

            if vuln.get('severity') == 'CRITICAL':
                critical_count += 1
            elif vuln.get('severity') == 'HIGH':
                high_count += 1

            if vuln.get('package_name'):
                packages_affected.add(vuln['package_name'])
            if vuln.get('package_manager'):
                package_managers.add(vuln['package_manager'])

    return {
        'vulnerabilities': unique_vulns,
        'summary': {
            'total': len(unique_vulns),
            'critical': critical_count,
            'high': high_count
        },
        'packages_affected': list(packages_affected),
        'package_managers': list(package_managers)
    }


def main():
    print("\n" + "="*60)
    print("  Inspector API Vulnerability Fetch Test")
    print("="*60)

    # 获取漏洞
    vulnerabilities = get_container_findings(REPO_NAME, IMAGE_DIGEST)

    # 聚合漏洞
    result = aggregate_vulnerabilities(vulnerabilities)

    # 打印结果
    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)

    summary = result['summary']
    print(f"\n📊 Summary:")
    print(f"   Total vulnerabilities: {summary['total']}")
    print(f"   CRITICAL: {summary['critical']}")
    print(f"   HIGH: {summary['high']}")
    print(f"   Affected packages: {len(result['packages_affected'])}")
    print(f"   Package managers: {result['package_managers']}")

    print(f"\n📦 Affected packages: {', '.join(sorted(result['packages_affected']))}")

    # 打印 CRITICAL 漏洞详情
    print(f"\n🔴 CRITICAL Vulnerabilities:")
    print("-" * 60)
    critical_vulns = [v for v in result['vulnerabilities'] if v['severity'] == 'CRITICAL']
    for i, vuln in enumerate(critical_vulns, 1):
        print(f"{i}. {vuln['cve_id']}")
        print(f"   Package: {vuln['package_name']} ({vuln['current_version']})")
        print(f"   Fixed in: {vuln['fixed_version']}")
        print(f"   CVSS: {vuln['cvss_score']}")
        print(f"   Exploit available: {'Yes' if vuln['exploit_available'] else 'No'}")
        print()

    # 打印 HIGH 漏洞详情
    print(f"\n🟠 HIGH Vulnerabilities:")
    print("-" * 60)
    high_vulns = [v for v in result['vulnerabilities'] if v['severity'] == 'HIGH']
    for i, vuln in enumerate(high_vulns, 1):
        print(f"{i}. {vuln['cve_id']}")
        print(f"   Package: {vuln['package_name']} ({vuln['current_version']})")
        print(f"   Fixed in: {vuln['fixed_version']}")
        print(f"   CVSS: {vuln['cvss_score']}")
        print(f"   Exploit available: {'Yes' if vuln['exploit_available'] else 'No'}")
        print()

    # 保存完整结果到文件
    output_file = "inspector_findings_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Full results saved to: {output_file}")

    return result


if __name__ == "__main__":
    main()
