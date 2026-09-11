"""Stress-test the SDL against 10 real-world scenarios from different platforms.

Each scenario attempts to faithfully represent a topology/exercise from
a known cyber range platform in RAES SDL format. This tests the
expressiveness boundaries of the language.
"""

import textwrap

import pytest
from raes import SDLParseError, SDLValidationError, parse_sdl


def _parse(yaml_str: str, label: str):
    """Parse SDL and report what worked and what didn't."""
    try:
        s = parse_sdl(textwrap.dedent(yaml_str))
        return s, None
    except (SDLParseError, SDLValidationError) as e:
        return None, e


# -----------------------------------------------------------------------
# 1. OCR SDL: Full exercise from their test suite
# -----------------------------------------------------------------------

OCR_FULL_EXERCISE = """
name: ocr-full-exercise
description: Full OCR SDL exercise with all 14 sections

nodes:
  main-switch:
    type: Switch
  win-10:
    type: compute
    source: windows10
    resources:
      ram: 4 gib
      cpu: 2
    roles:
      admin: admin-user
      defender:
        username: blue-user
        entities:
          - blue-team.bob
    features:
      apache-svc: admin
    conditions:
      service-check: admin
  deb-server:
    type: compute
    source:
      name: debian11
      version: "2.0.0"
    resources:
      ram: 2 gib
      cpu: 1

infrastructure:
  main-switch:
    count: 1
    properties:
      cidr: 10.10.10.0/24
      gateway: 10.10.10.1
  win-10:
    count: 1
    links:
      - main-switch
    properties:
      - main-switch: 10.10.10.10
  deb-server:
    links:
      - main-switch
    dependencies:
      - win-10

features:
  apache-svc:
    type: Service
    source: apache-package
  web-config:
    type: Configuration
    source:
      name: web-cfg
      version: 1.0.0
    dependencies:
      - apache-svc
  artifact-lib:
    type: Artifact
    source: dl-library
    destination: /opt/lib

conditions:
  service-check:
    proposition: service-ready
    command: /usr/local/bin/check.sh
    interval: 30
  lib-condition:
    source: checker-pkg

evidence_requirements:
  service-check-evidence:
    description: Capture the governed service readiness observation.
    source_refs: [nodes.win-10]
    scope_refs: [nodes.win-10]
    boundary_kind: assertion_evaluation
    channel: log
    artifact_role: proposition_truth_evidence
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required

propositions:
  service-ready:
    description: The governed service is ready for the event.
    subjects: [nodes.win-10]
    basis: observed_state
    predicate: {kind: boolean, property: service-ready, semantic_ref: urn:raes:observable:service-ready, operator: equals, expected: true}
    evidence_requirements: [service-check-evidence]

assertions:
  service-ready: {proposition: service-ready, role: precondition, polarity: positive}

entities:
  blue-team:
    name: Blue Team
    role: Blue
    entities:
      bob:
        name: Blue Bob
  red-team:
    name: Red Team
    role: Red

injects:
  attack-inject:
    source: attack-pkg
    from_entity: red-team
    to_entities:
      - blue-team

events:
  attack-event:
    assertions:
      - service-ready
    injects:
      - attack-inject

scripts:
  main-script:
    start_time: 5 min
    end_time: 2 hour
    speed: 1.0
    events:
      attack-event: 30 min

stories:
  main-story:
    speed: 1
    scripts:
      - main-script
"""


# -----------------------------------------------------------------------
# 2. CybORG CAGE-1 style: 3-host Metasploit vs Velociraptor
# -----------------------------------------------------------------------

CYBORG_CAGE1 = """
name: cyborg-cage1
description: >
  CybORG CAGE Challenge 1 topology: attacker, gateway, internal host,
  and a defender running Velociraptor.

nodes:
  attacker-net:
    type: Switch
  defender-net:
    type: Switch
  private-net:
    type: Switch
  attacker:
    type: compute
    source: kali-box
    resources:
      ram: 2 gib
      cpu: 2
  gateway:
    type: compute
    source: ubuntu-gateway
    resources:
      ram: 1 gib
      cpu: 1
  internal:
    type: compute
    source: ubuntu-internal
    resources:
      ram: 1 gib
      cpu: 1
  defender:
    type: compute
    source: velociraptor-server
    resources:
      ram: 2 gib
      cpu: 1
    features:
      velociraptor-server: admin
    roles:
      admin: ubuntu

infrastructure:
  attacker-net:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
  defender-net:
    count: 1
    properties:
      cidr: 10.0.1.0/24
      gateway: 10.0.1.1
  private-net:
    count: 1
    properties:
      cidr: 10.0.2.0/24
      gateway: 10.0.2.1
  attacker:
    count: 1
    links:
      - attacker-net
  gateway:
    count: 1
    links:
      - private-net
      - attacker-net
  internal:
    count: 1
    links:
      - private-net
  defender:
    count: 1
    links:
      - defender-net
      - private-net

features:
  velociraptor-server:
    type: Service
    source: velociraptor

entities:
  red-agent:
    name: Red Agent
    role: Red
  blue-agent:
    name: Blue Agent
    role: Blue
"""


# -----------------------------------------------------------------------
# 3. CybORG CAGE-2 style: 13-host enterprise with OT
# -----------------------------------------------------------------------

CYBORG_CAGE2 = """
name: cyborg-cage2
description: >
  CybORG CAGE Challenge 2: 13-host enterprise with user, enterprise,
  and operational segments. Red/Blue/Green agents.

nodes:
  user-net:
    type: Switch
  enterprise-net:
    type: Switch
  operational-net:
    type: Switch
  user0:
    type: compute
    source: windows-user
    resources: {ram: 1 gib, cpu: 1}
  user1:
    type: compute
    source: windows-user
    resources: {ram: 1 gib, cpu: 1}
  user2:
    type: compute
    source: windows-user
    resources: {ram: 1 gib, cpu: 1}
  user3:
    type: compute
    source: windows-user
    resources: {ram: 1 gib, cpu: 1}
  user4:
    type: compute
    source: windows-user
    resources: {ram: 1 gib, cpu: 1}
  enterprise0:
    type: compute
    source: gateway
    resources: {ram: 1 gib, cpu: 1}
  enterprise1:
    type: compute
    source: internal-server
    resources: {ram: 1 gib, cpu: 1}
  enterprise2:
    type: compute
    source: internal-server
    resources: {ram: 1 gib, cpu: 1}
  defender:
    type: compute
    source: velociraptor-server
    resources: {ram: 2 gib, cpu: 2}
  op-server0:
    type: compute
    source: ot-server
    resources: {ram: 1 gib, cpu: 1}
  op-host0:
    type: compute
    source: ot-host
    resources: {ram: 1 gib, cpu: 1}
  op-host1:
    type: compute
    source: ot-host
    resources: {ram: 1 gib, cpu: 1}
  op-host2:
    type: compute
    source: ot-host
    resources: {ram: 1 gib, cpu: 1}

infrastructure:
  user-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  enterprise-net:
    count: 1
    properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1}
  operational-net:
    count: 1
    properties: {cidr: 10.0.2.0/24, gateway: 10.0.2.1}
  user0: {count: 1, links: [user-net]}
  user1: {count: 1, links: [user-net]}
  user2: {count: 1, links: [user-net]}
  user3: {count: 1, links: [user-net]}
  user4: {count: 1, links: [user-net]}
  enterprise0: {count: 1, links: [enterprise-net, user-net]}
  enterprise1: {count: 1, links: [enterprise-net]}
  enterprise2: {count: 1, links: [enterprise-net]}
  defender: {count: 1, links: [enterprise-net]}
  op-server0: {count: 1, links: [operational-net, enterprise-net]}
  op-host0: {count: 1, links: [operational-net]}
  op-host1: {count: 1, links: [operational-net]}
  op-host2: {count: 1, links: [operational-net]}

entities:
  red:
    name: Red Agent
    role: Red
  blue:
    name: Blue Agent
    role: Blue
  green:
    name: Green Agent (normal users)
    role: Green
"""


# -----------------------------------------------------------------------
# 4. CALDERA-style: Ransack adversary profile (multi-step data theft)
# -----------------------------------------------------------------------

CALDERA_RANSACK = """
name: caldera-ransack
description: >
  CALDERA Ransack adversary profile modeled as SDL: data theft
  with exfiltration check via OCR scoring pipeline.

nodes:
  lab-net: {type: Switch}
  victim: {type: compute, os: linux, resources: {ram: 2 gib, cpu: 1}}
  kali: {type: compute, os: linux, resources: {ram: 2 gib, cpu: 2}}

infrastructure:
  lab-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  victim: {count: 1, links: [lab-net]}
  kali: {count: 1, links: [lab-net]}

conditions:
  exfil-check:
    command: "test -f /home/kali/operations/exfil/loot.tar.gz"
    interval: 30

entities:
  attacker: {name: Ransack Operator, role: Red}
"""


# -----------------------------------------------------------------------
# 5. Atomic Red Team style: credential dumping test battery
# -----------------------------------------------------------------------

ATOMIC_CRED_DUMP = """
name: atomic-credential-dumping
description: >
  Atomic Red Team T1003.001 credential dumping modeled as SDL:
  Windows target with weak credentials, manual grading via metrics.

nodes:
  lab-net: {type: Switch}
  target:
    type: compute
    os: windows
    os_distribution: windows-client
    os_version: "10"
    resources: {ram: 4 gib, cpu: 2}

infrastructure:
  lab-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  target: {count: 1, links: [lab-net]}

entities:
  pentester: {name: Penetration Tester, role: Red}
"""


# -----------------------------------------------------------------------
# 6. CyRIS-style: DMZ with firewall rules
# -----------------------------------------------------------------------

CYRIS_DMZ = """
name: cyris-dmz-topology
description: >
  CyRIS-style DMZ topology with web server, database, and firewall.
  Models a basic enterprise perimeter.

nodes:
  wan-switch:
    type: Switch
  dmz-switch:
    type: Switch
  lan-switch:
    type: Switch
  firewall:
    type: compute
    source: pfsense
    resources: {ram: 512 mib, cpu: 1}
    features:
      fw-rules: admin
    roles:
      admin: root
  webserver:
    type: compute
    source: ubuntu-apache
    resources: {ram: 1 gib, cpu: 1}
    features:
      apache-web: www
      php-app: www
    conditions:
      http-alive: www
    roles:
      www: www-data
  database:
    type: compute
    source: ubuntu-mysql
    resources: {ram: 1 gib, cpu: 1}
    features:
      mysql-server: dba
    conditions:
      mysql-alive: dba
    roles:
      dba: mysql
  attacker:
    type: compute
    source: kali-linux
    resources: {ram: 2 gib, cpu: 2}

infrastructure:
  wan-switch:
    count: 1
    properties: {cidr: 192.168.1.0/24, gateway: 192.168.1.1}
  dmz-switch:
    count: 1
    properties: {cidr: 172.16.0.0/24, gateway: 172.16.0.1}
  lan-switch:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  firewall:
    count: 1
    links: [wan-switch, dmz-switch, lan-switch]
  webserver:
    count: 1
    links: [dmz-switch]
    dependencies: [firewall]
  database:
    count: 1
    links: [lan-switch]
    dependencies: [firewall]
  attacker:
    count: 1
    links: [wan-switch]

features:
  fw-rules:
    type: Configuration
    source: pfsense-rules
    description: Firewall rules allowing HTTP to DMZ, deny LAN from WAN
  apache-web:
    type: Service
    source: apache2
  php-app:
    type: Service
    source: vulnerable-php-app
    dependencies: [apache-web]
  mysql-server:
    type: Service
    source: mysql-5.7

conditions:
  http-alive:
    command: "curl -sf http://localhost/ || exit 1"
    interval: 15
  mysql-alive:
    command: "mysqladmin ping -u root"
    interval: 15

"""


# -----------------------------------------------------------------------
# 7. KYPO-style: CTF training with scoring
# -----------------------------------------------------------------------

KYPO_CTF = """
name: kypo-ctf-training
description: >
  KYPO-style CTF training exercise with multi-level challenges
  and progressive hints.

nodes:
  training-net:
    type: Switch
  challenge-server:
    type: compute
    source: ubuntu-ctf
    resources: {ram: 2 gib, cpu: 2}
  scoreboard:
    type: compute
    source: ctfd-server
    resources: {ram: 1 gib, cpu: 1}

infrastructure:
  training-net:
    count: 1
    properties: {cidr: 10.10.0.0/24, gateway: 10.10.0.1}
  challenge-server:
    count: 1
    links: [training-net]
  scoreboard:
    count: 1
    links: [training-net]

entities:
  trainers:
    name: Training Staff
    role: White
  participants:
    name: CTF Participants
    role: Blue
    entities:
      team-alpha:
        name: Team Alpha
      team-bravo:
        name: Team Bravo

conditions:
  flag-check-1:
    command: "/opt/ctf/check_flag.sh level1"
    interval: 10
  flag-check-2:
    command: "/opt/ctf/check_flag.sh level2"
    interval: 10
  flag-check-3:
    command: "/opt/ctf/check_flag.sh level3"
    interval: 10
"""


# -----------------------------------------------------------------------
# 8. Hack The Box style: single-machine challenge
# -----------------------------------------------------------------------

HTB_MACHINE = """
name: htb-style-machine
description: >
  Hack The Box style single-machine challenge. Web app initial access,
  privilege escalation to root.

nodes:
  challenge-net:
    type: Switch
  target:
    type: compute
    source: htb-machine-easy
    resources: {ram: 1 gib, cpu: 1}
    features:
      nginx-web: www
      vulnerable-api: www
    conditions:
      web-health: www
    roles:
      www: www-data
      user: htb-user
      root: root

infrastructure:
  challenge-net:
    count: 1
    properties: {cidr: 10.10.10.0/24, gateway: 10.10.10.1}
  target:
    count: 1
    links: [challenge-net]
    properties:
      - challenge-net: 10.10.10.50

features:
  nginx-web:
    type: Service
    source: nginx
  vulnerable-api:
    type: Service
    source: nodejs-api
    dependencies: [nginx-web]

conditions:
  web-health:
    command: "curl -sf http://localhost:80/ || exit 1"
    interval: 15

"""


# -----------------------------------------------------------------------
# 9. Enterprise AD lab: multi-forest with trust relationships
# -----------------------------------------------------------------------

ENTERPRISE_AD = """
name: enterprise-ad-lab
description: >
  Enterprise Active Directory lab with parent and child domains,
  trust relationships, and multi-tier architecture.

nodes:
  corp-net:
    type: Switch
  dmz-net:
    type: Switch
  mgmt-net:
    type: Switch
  dc01:
    type: compute
    source: windows-server-2022
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-forest-root: admin}
    roles: {admin: Administrator}
  dc02:
    type: compute
    source: windows-server-2022
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-child-domain: admin}
    roles: {admin: Administrator}
  exchange:
    type: compute
    source: windows-server-2019
    resources: {ram: 8 gib, cpu: 4}
    features: {exchange-server: admin}
    roles: {admin: Administrator}
  fileserver:
    type: compute
    source: windows-server-2022
    resources: {ram: 2 gib, cpu: 1}
  ws01:
    type: compute
    source: windows-10-enterprise
    resources: {ram: 4 gib, cpu: 2}
  ws02:
    type: compute
    source: windows-10-enterprise
    resources: {ram: 4 gib, cpu: 2}
  linux-jump:
    type: compute
    source: ubuntu-22.04
    resources: {ram: 1 gib, cpu: 1}
    features: {ssh-bastion: admin}
    conditions: {ssh-alive: admin}
    roles:
      admin: sysadmin

infrastructure:
  corp-net:
    count: 1
    properties: {cidr: 10.0.0.0/16, gateway: 10.0.0.1}
  dmz-net:
    count: 1
    properties: {cidr: 172.16.0.0/24, gateway: 172.16.0.1}
  mgmt-net:
    count: 1
    properties: {cidr: 192.168.100.0/24, gateway: 192.168.100.1}
  dc01: {count: 1, links: [corp-net]}
  dc02: {count: 1, links: [corp-net], dependencies: [dc01]}
  exchange: {count: 1, links: [corp-net, dmz-net], dependencies: [dc01]}
  fileserver: {count: 1, links: [corp-net]}
  ws01: {count: 1, links: [corp-net]}
  ws02: {count: 1, links: [corp-net]}
  linux-jump: {count: 1, links: [dmz-net, mgmt-net]}

features:
  ad-forest-root:
    type: Service
    source: adds-forest-root
    description: AD DS forest root (corp.local)
  ad-child-domain:
    type: Service
    source: adds-child
    dependencies: [ad-forest-root]
    description: Child domain (dev.corp.local)
  exchange-server:
    type: Service
    source: exchange-2019
    dependencies: [ad-forest-root]
  ssh-bastion:
    type: Service
    source: openssh-server

conditions:
  ssh-alive:
    command: "ss -tlnp | grep ':22' || exit 1"
    interval: 15

"""


# -----------------------------------------------------------------------
# 10. Cloud-hybrid: AWS VPC + on-prem with VPN tunnel
# -----------------------------------------------------------------------

CLOUD_HYBRID = """
name: cloud-hybrid-scenario
description: >
  Hybrid cloud/on-prem topology modeling an AWS VPC connected
  to on-premises network via VPN. Tests SDL with cloud-like
  topology patterns.

nodes:
  aws-vpc:
    type: Switch
    description: AWS VPC (simulated)
  onprem-lan:
    type: Switch
    description: On-premises corporate LAN
  vpn-tunnel:
    type: Switch
    description: Site-to-site VPN tunnel
  web-alb:
    type: compute
    source: nginx-proxy
    resources: {ram: 512 mib, cpu: 1}
    description: Application load balancer
  app-server-1:
    type: compute
    source: nodejs-app
    resources: {ram: 2 gib, cpu: 2}
    features: {node-app: app-svc}
    roles: {app-svc: node}
  app-server-2:
    type: compute
    source: nodejs-app
    resources: {ram: 2 gib, cpu: 2}
    features: {node-app: app-svc}
    roles: {app-svc: node}
  rds-primary:
    type: compute
    source: postgres-14
    resources: {ram: 4 gib, cpu: 2}
    features: {postgres-db: dba}
    conditions: {pg-health: dba}
    roles:
      dba: postgres
  onprem-dc:
    type: compute
    source: windows-server-2019
    resources: {ram: 4 gib, cpu: 2}
    description: On-premises domain controller
  onprem-workstation:
    type: compute
    source: windows-10
    resources: {ram: 4 gib, cpu: 2}

infrastructure:
  aws-vpc:
    count: 1
    properties: {cidr: 10.0.0.0/16, gateway: 10.0.0.1}
  onprem-lan:
    count: 1
    properties: {cidr: 192.168.0.0/16, gateway: 192.168.0.1}
  vpn-tunnel:
    count: 1
    properties: {cidr: 169.254.0.0/30, gateway: 169.254.0.1}
  web-alb: {count: 1, links: [aws-vpc]}
  app-server-1: {count: 1, links: [aws-vpc], dependencies: [rds-primary]}
  app-server-2: {count: 1, links: [aws-vpc], dependencies: [rds-primary]}
  rds-primary: {count: 1, links: [aws-vpc]}
  onprem-dc: {count: 1, links: [onprem-lan]}
  onprem-workstation: {count: 1, links: [onprem-lan]}

features:
  node-app:
    type: Service
    source: express-api
  postgres-db:
    type: Service
    source: postgresql-14

conditions:
  pg-health:
    command: "pg_isready"
    interval: 10

"""


# =======================================================================
# Test execution
# =======================================================================

# -----------------------------------------------------------------------
# 11. Exchange server with mailboxes, accounts, ACLs, and content
# -----------------------------------------------------------------------

EXCHANGE_WITH_DATA = """
name: exchange-phishing-exercise
description: >
  Exchange server with user accounts, phishing lure emails, sensitive
  financial data, and network access controls. Tests the content,
  accounts, ACLs, services, os, and asset_value extensions.

nodes:
  corp-net:
    type: Switch
  dmz-net:
    type: Switch
  exchange:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2019"
    source: exchange-2019
    resources: {ram: 8 gib, cpu: 4}
    features: [exchange-server, outlook-web]
    services:
      - port: 443
        protocol: tcp
        name: https
      - port: 25
        protocol: tcp
        name: smtp
      - port: 587
        protocol: tcp
        name: submission
    asset_value:
      confidentiality: high
      integrity: high
      availability: critical
  dc:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2022"
    source: windows-server-2022
    resources: {ram: 4 gib, cpu: 2}
    features: [ad-ds]
  attacker:
    type: compute
    os: linux
    source: kali
    resources: {ram: 2 gib, cpu: 2}

infrastructure:
  corp-net:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
      internal: true
  dmz-net:
    count: 1
    properties:
      cidr: 172.16.0.0/24
      gateway: 172.16.0.1
    acls:
      - direction: in
        from_net: corp-net
        protocol: tcp
        ports: [443, 25]
        action: allow
      - direction: out
        to_net: corp-net
        action: deny
  exchange: {count: 1, links: [corp-net, dmz-net]}
  dc: {count: 1, links: [corp-net]}
  attacker: {count: 1, links: [dmz-net]}

features:
  exchange-server:
    type: Service
    source: exchange-2019
  outlook-web:
    type: Service
    dependencies: [exchange-server]
    source: owa-frontend
  ad-ds:
    type: Service
    source: adds-forest-root

identity_domains:
  techvault:
    profile: active_directory
    dns_name: techvault.local
    netbios_name: TECHVAULT
    authority_account_ref: svc-backup

accounts:
  ceo:
    username: ceo
    node: exchange
    groups: [Domain Admins, Executives]
    mail: ceo@techvault.local
    password_strength: strong
  cfo:
    username: cfo
    node: exchange
    groups: [Finance, Executives]
    mail: cfo@techvault.local
    password_strength: strong
  finance-analyst:
    username: jsmith
    node: exchange
    groups: [Finance]
    mail: jsmith@techvault.local
    password_strength: weak
    description: "Target for spearphishing - weak password"
  svc-backup:
    username: svc_backup
    node: dc
    groups: [Backup Operators]
    password_strength: weak
    spn: "MSSQL/db.techvault.local"
    domain_ref: techvault
    description: "Kerberoastable service account"

relationships:
  dc-controls-techvault-domain:
    type: domain_controller_for
    source: dc
    target: techvault
    domain_controller: {}

content:
  phishing-lures:
    type: dataset
    target: exchange
    destination: /var/mail/jsmith/
    format: eml
    description: "Spearphishing emails targeting finance analyst"
    sensitive: true
    items:
      - name: q3-budget-review
        display_name: "Q3 Budget Review - Action Required.eml"
        tags: [phishing, attachment, macro]
      - name: urgent-wire-transfer
        display_name: "Urgent Wire Transfer Approval.eml"
        tags: [phishing, link, credential-harvesting]
      - name: updated-benefits-enrollment
        display_name: "Updated Benefits Enrollment.eml"
        tags: [phishing, attachment, exe-in-zip]
  sensitive-financials:
    type: dataset
    target: exchange
    destination: /var/mail/cfo/
    format: eml
    description: "Legitimate confidential financial emails"
    sensitive: true
    items:
      - name: board-minutes-q3
        display_name: "Board Minutes - Q3 Confidential.eml"
        tags: [pii, financial, exfil-target]
      - name: merger-target-list
        display_name: "M&A Target List - Internal Only.eml"
        tags: [financial, exfil-target]
  planted-webshell:
    type: file
    target: exchange
    path: /inetpub/wwwroot/aspnet_client/shell.aspx
    description: "Pre-staged webshell simulating ProxyLogon exploitation"
    sensitive: true
    tags: [webshell, initial-access]

entities:
  red-team:
    name: Red Team
    role: Red
    mission: "Exploit Exchange via ProxyLogon, exfiltrate financial data"
  blue-team:
    name: Blue Team
    role: Blue
    mission: "Detect Exchange compromise, contain lateral movement"
    entities:
      soc-analyst:
        name: SOC Analyst
"""


# -----------------------------------------------------------------------
# 12. CybORG CAGE-2 with agents, relationships, accounts
# -----------------------------------------------------------------------

CYBORG_WITH_AGENTS = """
name: cyborg-cage2-agents
description: >
  CybORG CAGE-2 with red/blue/green agents, starting accounts,
  initial knowledge, allowed subnets, and service relationships.

nodes:
  user-net: {type: Switch}
  enterprise-net: {type: Switch}
  op-net: {type: Switch}
  user0: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  user1: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  enterprise0: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  enterprise1: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  defender: {type: compute, os: linux, resources: {ram: 2 gib, cpu: 2}, features: {velociraptor: velo-admin}, roles: {velo-admin: ubuntu}}
  op-server0: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}

infrastructure:
  user-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  enterprise-net: {count: 1, properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1}}
  op-net: {count: 1, properties: {cidr: 10.0.2.0/24, gateway: 10.0.2.1, internal: true}}
  user0: {count: 1, links: [user-net]}
  user1: {count: 1, links: [user-net]}
  enterprise0: {count: 1, links: [enterprise-net, user-net]}
  enterprise1: {count: 1, links: [enterprise-net]}
  defender: {count: 1, links: [enterprise-net]}
  op-server0: {count: 1, links: [op-net, enterprise-net]}

features:
  velociraptor: {type: Service, source: velociraptor-server}

conditions:
  enterprise0-compromised:
    proposition: enterprise0-compromised
    command: /usr/bin/check-enterprise0-compromise
    interval: 60
  enterprise0-detected:
    proposition: enterprise0-detected
    command: /usr/bin/check-enterprise0-detection
    interval: 60

evidence_requirements:
  enterprise0-state-evidence:
    description: Capture governed enterprise0 state observations.
    source_refs: [nodes.enterprise0]
    scope_refs: [nodes.enterprise0]
    boundary_kind: assertion_evaluation
    channel: log
    artifact_role: proposition_truth_evidence
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required

propositions:
  enterprise0-compromised:
    description: The governed enterprise0 host is compromised.
    subjects: [nodes.enterprise0]
    basis: observed_state
    predicate: {kind: boolean, property: compromised, semantic_ref: urn:raes:observable:compromised, operator: equals, expected: true}
    evidence_requirements: [enterprise0-state-evidence]
  enterprise0-detected:
    description: Compromise of the governed enterprise0 host was detected.
    subjects: [nodes.enterprise0]
    basis: observed_state
    predicate: {kind: boolean, property: compromise-detected, semantic_ref: urn:raes:observable:compromise-detected, operator: equals, expected: true}
    evidence_requirements: [enterprise0-state-evidence]

assertions:
  enterprise0-compromised: {proposition: enterprise0-compromised, role: postcondition, polarity: positive}
  enterprise0-detected: {proposition: enterprise0-detected, role: postcondition, polarity: positive}

accounts:
  phished-user:
    username: jdoe
    node: user0
    password_strength: weak
    description: "Initial foothold via spearphishing"
  soc-admin:
    username: soc-analyst
    node: defender
    password_strength: strong
  green-user:
    username: employee
    node: user0
    password_strength: medium

entities:
  red-team: {name: Red Team, role: Red}
  blue-team:
    name: Blue Team
    role: Blue
    entities:
      analyst: {name: SOC Analyst}
  green-team: {name: Normal Users, role: Green}

agents:
  red-agent:
    entity: red-team
    actions: [DiscoverRemoteSystems, DiscoverNetworkServices, ExploitRemoteService, EternalBlue, SSHBruteForce, PrivilegeEscalate, Impact]
    starting_accounts: [phished-user]
    initial_knowledge:
      hosts: [user0]
      subnets: [user-net]
    allowed_subnets: [user-net, enterprise-net]

  blue-agent:
    entity: blue-team.analyst
    actions: [Monitor, Analyse, Remove, Restore, DecoyApache, DecoySSHD]
    starting_accounts: [soc-admin]
    initial_knowledge:
      hosts: [defender, enterprise0, enterprise1, user0, user1]
      subnets: [user-net, enterprise-net, op-net]
    allowed_subnets: [user-net, enterprise-net, op-net]

  green-agent:
    entity: green-team
    actions: [NormalBrowsing, EmailCheck, FileAccess]
    starting_accounts: [green-user]
    allowed_subnets: [user-net]
    description: "Simulates normal user behavior"

relationships:
  velo-monitors-enterprise:
    type: manages
    source: velociraptor
    target: enterprise0
    description: "Velociraptor monitors enterprise hosts"

events:
  phishing-wave: {}
  triage-window: {}

scripts:
  day-1:
    start_time: 0
    end_time: 2 hour
    speed: 1
    events:
      phishing-wave: 5 min
      triage-window: 45 min

stories:
  exercise:
    scripts: [day-1]

objectives:
  red-establish-foothold:
    agent: red-agent
    actions: [DiscoverRemoteSystems, ExploitRemoteService, EternalBlue]
    targets: [enterprise0]
    success:
      assertions: [enterprise0-compromised]
    window:
      stories: [exercise]
      scripts: [day-1]
      events: [phishing-wave]

  blue-detect-and-report:
    agent: blue-agent
    actions: [Monitor, Analyse]
    targets: [enterprise0, velociraptor]
    success:
      assertions: [enterprise0-detected]
    window:
      stories: [exercise]
      scripts: [day-1]
      events: [triage-window]
    depends_on: [red-establish-foothold]
"""


# -----------------------------------------------------------------------
# 13. Multi-domain AD with trust, federation, and variables
# -----------------------------------------------------------------------

AD_TRUST_FEDERATED = """
name: multi-domain-ad-trust
description: >
  Multi-domain AD with parent-child trust, ADFS federation to
  cloud IdP, parameterized via variables, service relationships.

variables:
  domain_name:
    type: string
    default: "corp.local"
    description: "Root AD domain name"
  child_domain:
    type: string
    default: "dev.corp.local"
    description: "Child AD domain name"
  workstation_count:
    type: integer
    default: 3
    description: "Number of employee workstations"

nodes:
  corp-net: {type: Switch}
  dmz-net: {type: Switch}
  dc01:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2022"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-forest-root: admin}
    roles: {admin: Administrator}
  dc02:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2022"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-child-domain: admin}
    roles: {admin: Administrator}
  adfs:
    type: compute
    os: windows
    resources: {ram: 2 gib, cpu: 1}
    features: {adfs-service: admin}
    roles: {admin: Administrator}
  ws01:
    type: compute
    os: windows
    resources: {ram: 4 gib, cpu: 2}

infrastructure:
  corp-net: {count: 1, properties: {cidr: 10.0.0.0/16, gateway: 10.0.0.1, internal: true}}
  dmz-net: {count: 1, properties: {cidr: 172.16.0.0/24, gateway: 172.16.0.1}}
  dc01: {count: 1, links: [corp-net]}
  dc02: {count: 1, links: [corp-net], dependencies: [dc01]}
  adfs: {count: 1, links: [corp-net, dmz-net], dependencies: [dc01]}
  ws01: {count: 1, links: [corp-net]}

features:
  ad-forest-root:
    type: Service
    source: adds-forest
    description: "AD DS forest root domain"
  ad-child-domain:
    type: Service
    source: adds-child
    dependencies: [ad-forest-root]
    description: "AD DS child domain"
  adfs-service:
    type: Service
    source: adfs-2019
    dependencies: [ad-forest-root]
    description: "AD Federation Services for SSO"

identity_domains:
  corp:
    profile: active_directory
    dns_name: ${domain_name}
    netbios_name: CORP
    authority_account_ref: domain-admin
  dev:
    profile: active_directory
    dns_name: ${child_domain}
    netbios_name: DEV
    authority_account_ref: child-admin

accounts:
  domain-admin:
    username: Administrator
    node: dc01
    groups: [Domain Admins, Enterprise Admins]
    password_strength: strong
  svc-sql:
    username: svc_mssql
    node: dc01
    groups: [Domain Users]
    password_strength: weak
    spn: "MSSQL/db.corp.local"
    domain_ref: corp
    description: "Kerberoastable service account"
  child-admin:
    username: Administrator
    node: dc02
    groups: [Domain Admins]
    password_strength: strong
  employee:
    username: jdoe
    node: ws01
    groups: [Domain Users]
    password_strength: medium
    mail: "jdoe@corp.local"

relationships:
  dc01-controls-corp-domain:
    type: domain_controller_for
    source: dc01
    target: corp
    domain_controller: {}
  dc02-controls-dev-domain:
    type: domain_controller_for
    source: dc02
    target: dev
    domain_controller: {}
  adfs-joins-corp-domain:
    type: joins_domain
    source: adfs
    target: corp
    domain_join:
      controller_refs: [dc01]
  ws01-joins-corp-domain:
    type: joins_domain
    source: ws01
    target: corp
    domain_join:
      controller_refs: [dc01]
  child-trusts-parent:
    type: trusts
    source: ad-child-domain
    target: ad-forest-root
    description: "Child domain trusts forest root (automatic)"
    properties:
      trust_type: parent-child
      trust_direction: bidirectional

  adfs-authenticates-via-ad:
    type: authenticates_with
    source: adfs-service
    target: ad-forest-root
    description: "ADFS authenticates users against AD"

  adfs-federates-cloud:
    type: federates_with
    source: adfs-service
    target: adfs-service
    description: "ADFS provides SAML federation to cloud apps"
    properties:
      protocol: SAML
      idp_type: on-premises

entities:
  red-team: {name: Red Team, role: Red}
  blue-team: {name: Blue Team, role: Blue}

conditions:
  federation-service-up:
    proposition: federation-service-up
    command: /usr/bin/check-adfs-federation
    interval: 60

evidence_requirements:
  federation-state-evidence:
    description: Capture governed federation service observations.
    source_refs: [nodes.adfs]
    scope_refs: [nodes.adfs]
    boundary_kind: assertion_evaluation
    channel: log
    artifact_role: proposition_truth_evidence
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required

propositions:
  federation-service-up:
    description: The governed federation service is available.
    subjects: [nodes.adfs]
    basis: observed_state
    predicate: {kind: boolean, property: federation-service-up, semantic_ref: urn:raes:observable:federation-service-up, operator: equals, expected: true}
    evidence_requirements: [federation-state-evidence]

assertions:
  federation-service-up: {proposition: federation-service-up, role: postcondition, polarity: positive}

events:
  federation-cutover: {}

scripts:
  identity-day:
    start_time: 0
    end_time: 4 hour
    speed: 1
    events:
      federation-cutover: 30 min

stories:
  federation-exercise:
    scripts: [identity-day]

objectives:
  preserve-federated-auth:
    entity: blue-team
    targets: [adfs-service, child-trusts-parent]
    success:
      assertions: [federation-service-up]
    window:
      stories: [federation-exercise]
      scripts: [identity-day]
      events: [federation-cutover]
"""


SCENARIOS = [
    ("1. OCR Full Exercise (14 sections)", OCR_FULL_EXERCISE),
    ("2. CybORG CAGE-1 (3-host, Metasploit)", CYBORG_CAGE1),
    ("3. CybORG CAGE-2 (13-host enterprise+OT)", CYBORG_CAGE2),
    ("4. CALDERA Ransack (multi-step attack)", CALDERA_RANSACK),
    ("5. Atomic Red Team (credential dumping)", ATOMIC_CRED_DUMP),
    ("6. CyRIS DMZ (firewall + web + db)", CYRIS_DMZ),
    ("7. KYPO CTF (training + scoring)", KYPO_CTF),
    ("8. HTB Machine (single-box challenge)", HTB_MACHINE),
    ("9. Enterprise AD (multi-domain forest)", ENTERPRISE_AD),
    ("10. Cloud Hybrid (AWS VPC + on-prem VPN)", CLOUD_HYBRID),
    ("11. Exchange with data+accounts+ACLs", EXCHANGE_WITH_DATA),
    ("12. CybORG CAGE-2 with agents", CYBORG_WITH_AGENTS),
    ("13. Multi-domain AD with trust+federation", AD_TRUST_FEDERATED),
]


@pytest.mark.parametrize("label,yaml_str", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_parses_and_validates(label, yaml_str):
    """Each real-world scenario must parse and pass semantic validation."""
    scenario, error = _parse(yaml_str, label)
    assert error is None, f"{label} failed: {error}"
    assert scenario is not None

    # Verify the scenario has meaningful content
    has_nodes = bool(scenario.nodes)
    has_features = bool(scenario.features)
    has_stories = bool(scenario.stories)
    has_entities = bool(scenario.entities)
    has_objectives = bool(scenario.objectives)
    has_content = bool(scenario.content)
    assert any([has_nodes, has_features, has_stories, has_entities, has_objectives, has_content]), (
        f"{label} parsed but has no content"
    )


@pytest.mark.parametrize("label,yaml_str", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_topology_integrity(label, yaml_str):
    """Infrastructure references and node cross-references are consistent."""
    scenario = parse_sdl(textwrap.dedent(yaml_str))

    # Every infra entry should match a node
    for name in scenario.infrastructure:
        assert name in scenario.nodes, f"{label}: infra '{name}' has no matching node"

    # Every VM feature reference should exist in features
    for node_name, node in scenario.nodes.items():
        for feat_name in node.features:
            assert feat_name in scenario.features, f"{label}: node '{node_name}' refs missing feature '{feat_name}'"


def test_objectives_are_exercised_in_stress_suite():
    """Stress fixtures should include realistic objective-bearing scenarios."""
    labels_with_objectives: list[str] = []
    for label, yaml_str in SCENARIOS:
        scenario = parse_sdl(textwrap.dedent(yaml_str))
        if scenario.objectives:
            labels_with_objectives.append(label)

    assert len(labels_with_objectives) >= 2
