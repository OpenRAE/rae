"""Real-world scenario stress tests against the SDL.

Attempts to faithfully specify well-known cyber range scenarios from
published sources. Tests whether the SDL is expressive enough to
capture real-world topologies, services, vulnerabilities, attack paths,
team structures, and scoring — and identifies what it can't express.
"""

import textwrap

import pytest
from raes import SDLParseError, SDLValidationError, parse_sdl


def _parse(yaml_str: str, label: str):
    try:
        s = parse_sdl(textwrap.dedent(yaml_str))
        return s, None
    except (SDLParseError, SDLValidationError) as e:
        return None, e


# -----------------------------------------------------------------------
# 14. Incalmo/MHBench — Equifax-inspired multi-tier breach
# -----------------------------------------------------------------------

INCALMO_EQUIFAX = """
name: incalmo-equifax
description: >
  Equifax-inspired breach scenario from the Incalmo/MHBench benchmark.
  External web app with Apache Struts RCE, lateral movement via
  plaintext SSH credentials, 48 database targets with PII.

nodes:
  external-net:
    type: Switch
  dmz-net:
    type: Switch
  db-net:
    type: Switch

  web-frontend-1:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {apache-struts: www}
    services:
      - {port: 443, name: https}
      - {port: 8080, name: http-alt}
    roles: {www: www-data}
    asset_value: {confidentiality: low, availability: medium}

  web-frontend-2:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {apache-struts: www}
    services:
      - {port: 443, name: https}
    roles: {www: www-data}

  app-server:
    type: compute
    os: linux
    resources: {ram: 4 gib, cpu: 2}
    features: {java-backend: app}
    services:
      - {port: 8443, name: https}
    roles: {app: appuser}

  db-primary:
    type: compute
    os: linux
    resources: {ram: 8 gib, cpu: 4}
    features: {postgres-db: dba}
    services:
      - {port: 5432, name: postgresql}
    roles: {dba: postgres}
    asset_value: {confidentiality: critical, integrity: critical}

  db-replica-1:
    type: compute
    os: linux
    resources: {ram: 4 gib, cpu: 2}
    features: {postgres-db: dba}
    services: [{port: 5432, name: postgresql}]
    roles: {dba: postgres}
    asset_value: {confidentiality: critical}

  db-replica-2:
    type: compute
    os: linux
    resources: {ram: 4 gib, cpu: 2}
    features: {postgres-db: dba}
    services: [{port: 5432, name: postgresql}]
    roles: {dba: postgres}
    asset_value: {confidentiality: critical}

infrastructure:
  external-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  dmz-net:
    count: 1
    properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1, internal: true}
    acls:
      - {direction: in, from_net: external-net, protocol: tcp, ports: [443, 8080], action: allow}
      - {direction: in, from_net: external-net, action: deny}
  db-net:
    count: 1
    properties: {cidr: 10.0.2.0/24, gateway: 10.0.2.1, internal: true}
    acls:
      - {direction: in, from_net: dmz-net, protocol: tcp, ports: [5432], action: allow}
      - {direction: in, from_net: external-net, action: deny}
  web-frontend-1: {count: 1, links: [external-net, dmz-net]}
  web-frontend-2: {count: 1, links: [external-net, dmz-net]}
  app-server: {count: 1, links: [dmz-net, db-net]}
  db-primary: {count: 1, links: [db-net]}
  db-replica-1: {count: 1, links: [db-net]}
  db-replica-2: {count: 1, links: [db-net]}

features:
  apache-struts:
    type: Service
    source: apache-struts-2.5
    description: "Apache Struts 2 web framework (vulnerable version)"
  java-backend:
    type: Service
    source: spring-boot-api
  postgres-db:
    type: Service
    source: postgresql-12

content:
  pii-database:
    type: dataset
    target: db-primary
    format: sql
    source: equifax-pii-seed
    description: "145M synthetic customer records with SSN, DOB, addresses"
    sensitive: true
  ssh-creds-plaintext:
    type: file
    target: app-server
    path: /opt/app/config/db-credentials.properties
    text: "db.user=admin\\ndb.password=Equifax2017!"
    sensitive: true
    description: "Plaintext database credentials in config file"

accounts:
  web-service:
    username: www-data
    node: web-frontend-1
    password_strength: none
  app-service:
    username: appuser
    node: app-server
    password_strength: medium
  db-admin:
    username: admin
    node: db-primary
    password_strength: weak
    description: "Shared admin account with plaintext creds in config"

relationships:
  struts-to-backend:
    type: connects_to
    source: apache-struts
    target: java-backend
    properties: {protocol: http, port: "8443"}
  backend-to-db:
    type: authenticates_with
    source: java-backend
    target: postgres-db
    description: "Backend uses plaintext creds to connect to DB"
  db-replication:
    type: replicates_to
    source: postgres-db
    target: postgres-db
    description: "Primary replicates to all replicas"

entities:
  attacker:
    name: External Attacker
    role: Red
    mission: "Exfiltrate PII from database tier"
"""


# -----------------------------------------------------------------------
# 15. NICE Challenge 17 — Layered Defense
# -----------------------------------------------------------------------

NICE_CHALLENGE_17 = """
name: nice-challenge-17
description: >
  NICE Challenge 17 "Layered Defense": three-subnet enterprise with
  pfSense firewall, Joomla CMS, AD, fileshare, and database.

nodes:
  wan: {type: Switch}
  prodserv-net: {type: Switch}
  userspace-net: {type: Switch}
  infra-net: {type: Switch}

  pfsense:
    type: compute
    os: freebsd
    resources: {ram: 512 mib, cpu: 1}
    features: {firewall-rules: admin}
    services:
      - {port: 443, name: https}
    roles: {admin: admin}

  prod-joomla:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {joomla-cms: www, apache-web: www}
    services:
      - {port: 80, name: http}
      - {port: 443, name: https}
    roles: {www: www-data}

  workstation:
    type: compute
    os: windows
    os_distribution: windows-client
    os_version: "10"
    resources: {ram: 4 gib, cpu: 2}
    services: [{port: 3389, name: rdp}]

  ad-server:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2019"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-ds: admin, dns-server: admin}
    services:
      - {port: 53, protocol: udp, name: dns}
      - {port: 389, name: ldap}
      - {port: 445, name: smb}
    roles: {admin: Administrator}

  fileshare:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2019"
    resources: {ram: 2 gib, cpu: 1}
    features: {smb-shares: admin}
    services: [{port: 445, name: smb}]
    roles: {admin: Administrator}

  database:
    type: compute
    os: linux
    resources: {ram: 4 gib, cpu: 2}
    features: {mysql-server: dba}
    services: [{port: 3306, name: mysql}]
    roles: {dba: mysql}
    asset_value: {confidentiality: high}

infrastructure:
  wan: {count: 1, properties: {cidr: 203.0.113.0/24, gateway: 203.0.113.1}}
  prodserv-net: {count: 1, properties: {cidr: 172.16.10.0/24, gateway: 172.16.10.1, internal: true}}
  userspace-net: {count: 1, properties: {cidr: 172.16.20.0/24, gateway: 172.16.20.1, internal: true}}
  infra-net: {count: 1, properties: {cidr: 172.16.30.0/24, gateway: 172.16.30.1, internal: true}}
  pfsense: {count: 1, links: [wan, prodserv-net, userspace-net, infra-net]}
  prod-joomla: {count: 1, links: [prodserv-net]}
  workstation: {count: 1, links: [userspace-net]}
  ad-server: {count: 1, links: [infra-net]}
  fileshare: {count: 1, links: [infra-net]}
  database: {count: 1, links: [prodserv-net]}

features:
  firewall-rules: {type: Configuration, source: pfsense-rules}
  joomla-cms: {type: Service, source: joomla-3.9}
  apache-web: {type: Service, source: apache2}
  ad-ds: {type: Service, source: adds-2019}
  dns-server: {type: Service, source: windows-dns, dependencies: [ad-ds]}
  smb-shares: {type: Service, source: samba-shares}
  mysql-server: {type: Service, source: mysql-5.7}

relationships:
  joomla-to-mysql:
    type: connects_to
    source: joomla-cms
    target: mysql-server
  joomla-auth-ad:
    type: authenticates_with
    source: joomla-cms
    target: ad-ds

entities:
  blue-team: {name: Blue Team, role: Blue, mission: "Harden infrastructure and detect intrusions"}
  red-team: {name: Red Team, role: Red, mission: "Gain access and exfiltrate data"}
"""


# -----------------------------------------------------------------------
# 16. CCDC 2007 — Burnsodyne Industries
# -----------------------------------------------------------------------

CCDC_BURNSODYNE = """
name: ccdc-2007-burnsodyne
description: >
  CCDC 2007 National competition: Burnsodyne Industries. Each team
  defends 5 servers with 6 scored services. Red team attacks,
  scoring deducts for compromises.

nodes:
  team-net: {type: Switch}

  win2003-ad:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2003"
    resources: {ram: 1 gib, cpu: 1}
    features: {ad-ds: admin, iis-web: admin}
    services:
      - {port: 80, name: http}
      - {port: 443, name: https}
      - {port: 53, protocol: udp, name: dns}
    roles: {admin: Administrator}

  win2000-dns:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2000"
    resources: {ram: 512 mib, cpu: 1}
    features: {dns-server: admin, iis-web-2: admin}
    services:
      - {port: 53, protocol: udp, name: dns}
      - {port: 80, name: http}
    roles: {admin: Administrator}

  solaris-ecom:
    type: compute
    os: other
    os_distribution: solaris
    os_version: "10"
    resources: {ram: 1 gib, cpu: 1}
    features: {ecom-frontend: app}
    services:
      - {port: 443, name: https}
      - {port: 22, name: ssh}
    roles: {app: webadmin}

  ubuntu-backend:
    type: compute
    os: linux
    os_distribution: ubuntu
    os_version: "6.06"
    resources: {ram: 1 gib, cpu: 1}
    features: {ecom-backend: app, mysql-db: dba}
    services:
      - {port: 3306, name: mysql}
      - {port: 22, name: ssh}
    roles: {app: appuser, dba: mysql}

  freebsd-mail:
    type: compute
    os: freebsd
    resources: {ram: 512 mib, cpu: 1}
    features: {postfix-smtp: mail}
    services:
      - {port: 25, name: smtp}
      - {port: 22, name: ssh}
    roles: {mail: postfix}

infrastructure:
  team-net:
    count: 1
    properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}
  win2003-ad: {count: 1, links: [team-net]}
  win2000-dns: {count: 1, links: [team-net]}
  solaris-ecom: {count: 1, links: [team-net]}
  ubuntu-backend: {count: 1, links: [team-net]}
  freebsd-mail: {count: 1, links: [team-net]}

features:
  ad-ds: {type: Service, source: adds-2003}
  iis-web: {type: Service, source: iis-6}
  dns-server: {type: Service, source: win-dns}
  iis-web-2: {type: Service, source: iis-5}
  ecom-frontend: {type: Service, source: apache-ssl}
  ecom-backend: {type: Service, source: django-ecom}
  mysql-db: {type: Service, source: mysql-5.0}
  postfix-smtp: {type: Service, source: postfix}

conditions:
  http-scored: {command: "curl -sf http://localhost/ || exit 1", interval: 60}
  https-scored: {command: "curl -ksf https://localhost/ || exit 1", interval: 60}
  smtp-scored: {command: "echo QUIT | nc localhost 25 | grep 220", interval: 60}
  ssh-scored: {command: "ss -tlnp | grep :22 || exit 1", interval: 60}
  dns-scored: {command: "dig @localhost example.com +short || exit 1", interval: 60}
  mysql-scored: {command: "mysqladmin ping || exit 1", interval: 60}

entities:
  blue-team: {name: Blue Team, role: Blue, mission: "Maintain services, patch vulnerabilities"}
  red-team: {name: Red Team, role: Red, mission: "Compromise systems, steal PII"}
  white-team: {name: Scoring Engine, role: White, mission: "Score service availability"}
"""


# -----------------------------------------------------------------------
# 17. HTB ProLab Offshore-style — Multi-domain AD
# -----------------------------------------------------------------------

HTB_OFFSHORE = """
name: htb-offshore-style
description: >
  HTB ProLab "Offshore" inspired: multi-domain AD environment with
  4 domains, SQL injection entry, Kerberoasting, cross-domain trust
  abuse, DCSync. 21 machines, multiple pivot points.

nodes:
  entry-net: {type: Switch}
  corp-net: {type: Switch}
  dev-net: {type: Switch}
  admin-net: {type: Switch}

  web-portal:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {dotnet-webapp: www}
    services: [{port: 80, name: http}, {port: 443, name: https}]
    roles: {www: www-data}

  mssql-server:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2019"
    resources: {ram: 4 gib, cpu: 2}
    features: {mssql: dba}
    services: [{port: 1433, name: mssql}]
    roles: {dba: sa}

  dc-corp:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2022"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-corp: admin}
    services: [{port: 389, name: ldap}, {port: 88, name: kerberos}, {port: 445, name: smb}]
    roles: {admin: Administrator}

  dc-dev:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2019"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-dev: admin}
    services: [{port: 389, name: ldap}, {port: 88, name: kerberos}]
    roles: {admin: Administrator}

  exchange:
    type: compute
    os: windows
    resources: {ram: 8 gib, cpu: 4}
    features: {exchange-svc: admin}
    services: [{port: 443, name: https}, {port: 25, name: smtp}]
    roles: {admin: Administrator}

  jumpbox:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    services: [{port: 22, name: ssh}]

infrastructure:
  entry-net: {count: 1, properties: {cidr: 10.10.110.0/24, gateway: 10.10.110.1}}
  corp-net: {count: 1, properties: {cidr: 10.10.120.0/24, gateway: 10.10.120.1, internal: true}}
  dev-net: {count: 1, properties: {cidr: 10.10.130.0/24, gateway: 10.10.130.1, internal: true}}
  admin-net: {count: 1, properties: {cidr: 10.10.140.0/24, gateway: 10.10.140.1, internal: true}}
  web-portal: {count: 1, links: [entry-net]}
  mssql-server: {count: 1, links: [corp-net]}
  dc-corp: {count: 1, links: [corp-net, admin-net]}
  dc-dev: {count: 1, links: [dev-net, corp-net]}
  exchange: {count: 1, links: [corp-net]}
  jumpbox: {count: 1, links: [entry-net, corp-net]}

features:
  dotnet-webapp: {type: Service, source: aspnet-webapp}
  mssql: {type: Service, source: mssql-2019}
  ad-corp: {type: Service, source: adds-forest, description: "corp.offshore.local"}
  ad-dev: {type: Service, source: adds-child, dependencies: [ad-corp], description: "dev.corp.offshore.local"}
  exchange-svc: {type: Service, source: exchange-2019, dependencies: [ad-corp]}

identity_domains:
  corp:
    profile: active_directory
    dns_name: corp.offshore.local
    netbios_name: CORP
    authority_account_ref: da-corp
  dev:
    profile: active_directory
    dns_name: dev.corp.offshore.local
    netbios_name: DEV
    authority_account_ref: da-dev

accounts:
  svc-sql: {username: svc_mssql, node: dc-corp, password_strength: weak, spn: "MSSQL/mssql.corp.offshore.local", domain_ref: corp, groups: [Domain Users]}
  da-corp: {username: Administrator, node: dc-corp, domain_ref: corp, password_strength: strong, groups: [Domain Admins]}
  da-dev: {username: Administrator, node: dc-dev, domain_ref: dev, password_strength: strong, groups: [Domain Admins]}
  nopreauth-user: {username: svc_legacy, node: dc-corp, domain_ref: corp, password_strength: weak, description: "AS-REP roastable"}

relationships:
  dc-corp-controls-corp-domain:
    type: domain_controller_for
    source: dc-corp
    target: corp
    domain_controller: {}
  dc-dev-controls-dev-domain:
    type: domain_controller_for
    source: dc-dev
    target: dev
    domain_controller: {}
  exchange-joins-corp-domain:
    type: joins_domain
    source: exchange
    target: corp
    domain_join:
      controller_refs: [dc-corp]
  dev-trusts-corp:
    type: trusts
    source: ad-dev
    target: ad-corp
    properties: {trust_type: parent-child, trust_direction: bidirectional}
  webapp-to-mssql:
    type: connects_to
    source: dotnet-webapp
    target: mssql
  exchange-auth:
    type: authenticates_with
    source: exchange-svc
    target: ad-corp

entities:
  attacker: {name: Penetration Tester, role: Red, mission: "Compromise all 4 domains"}
"""


# -----------------------------------------------------------------------
# 18. Metasploitable 2 — Classic vulnerable lab
# -----------------------------------------------------------------------

METASPLOITABLE_2 = """
name: metasploitable-2
description: >
  Metasploitable 2: intentionally vulnerable Linux VM with 25+
  exploitable services. The canonical beginner pentest target.

nodes:
  lab-net: {type: Switch}

  metasploitable:
    type: compute
    os: linux
    os_distribution: ubuntu
    os_version: "8.04"
    resources: {ram: 512 mib, cpu: 1}
    features: [vsftpd, openssh, apache-web, samba-smb, mysql-db, postgres-db, unrealirc, distccd, java-rmi, tomcat-mgr, vnc-server]
    services:
      - {port: 21, name: ftp}
      - {port: 22, name: ssh}
      - {port: 23, name: telnet}
      - {port: 25, name: smtp}
      - {port: 80, name: http}
      - {port: 111, name: rpc}
      - {port: 139, name: netbios}
      - {port: 445, name: smb}
      - {port: 512, name: rexec}
      - {port: 513, name: rlogin}
      - {port: 514, name: rsh}
      - {port: 1099, name: java-rmi}
      - {port: 1524, name: ingreslock}
      - {port: 2049, name: nfs}
      - {port: 2121, name: ftp-alt}
      - {port: 3306, name: mysql}
      - {port: 3632, name: distccd}
      - {port: 5432, name: postgresql}
      - {port: 5900, name: vnc}
      - {port: 6000, name: x11}
      - {port: 6667, name: irc}
      - {port: 8009, name: ajp}
      - {port: 8180, name: tomcat}
    asset_value: {confidentiality: high}

  attacker:
    type: compute
    os: linux
    source: kali
    resources: {ram: 2 gib, cpu: 2}

infrastructure:
  lab-net: {count: 1, properties: {cidr: 192.168.1.0/24, gateway: 192.168.1.1}}
  metasploitable: {count: 1, links: [lab-net]}
  attacker: {count: 1, links: [lab-net]}

features:
  vsftpd: {type: Service, source: vsftpd-2.3.4, description: "vsftpd with backdoor (port 6200)"}
  openssh: {type: Service, source: openssh-4.7}
  apache-web: {type: Service, source: apache-2.2}
  samba-smb: {type: Service, source: samba-3.0}
  mysql-db: {type: Service, source: mysql-5.0}
  postgres-db: {type: Service, source: postgresql-8.3}
  unrealirc: {type: Service, source: unrealircd-3.2.8}
  distccd: {type: Service, source: distccd}
  java-rmi: {type: Service, source: java-rmi-registry}
  tomcat-mgr: {type: Service, source: tomcat-5.5}
  vnc-server: {type: Service, source: vnc4server}

accounts:
  msfadmin: {username: msfadmin, node: metasploitable, password_strength: weak}
  root-mysql: {username: root, node: metasploitable, password_strength: none, description: "MySQL root with no password"}
  postgres-user: {username: postgres, node: metasploitable, password_strength: weak}

entities:
  pentester: {name: Penetration Tester, role: Red}
"""


# -----------------------------------------------------------------------
# 19. Locked Shields style — IT/OT/SCADA defense
# -----------------------------------------------------------------------

LOCKED_SHIELDS_STYLE = """
name: locked-shields-style
description: >
  NATO Locked Shields inspired: fictional nation Berylia defending
  IT infrastructure, OT/SCADA power grid, and telecom systems.
  Generalized from publicly available descriptions.

nodes:
  it-net: {type: Switch}
  ot-net: {type: Switch}
  dmz-net: {type: Switch}
  scada-net: {type: Switch}

  ad-dc:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2022"
    resources: {ram: 4 gib, cpu: 2}
    features: {ad-berylia: admin}
    services: [{port: 389, name: ldap}, {port: 88, name: kerberos}, {port: 445, name: smb}]
    roles: {admin: Administrator}
    asset_value: {confidentiality: high, integrity: critical, availability: critical}

  mail-server:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {postfix-mail: mail}
    services: [{port: 25, name: smtp}, {port: 143, name: imap}, {port: 993, name: imaps}]
    roles: {mail: postfix}

  web-portal:
    type: compute
    os: linux
    resources: {ram: 2 gib, cpu: 1}
    features: {gov-website: www}
    services: [{port: 80, name: http}, {port: 443, name: https}]
    roles: {www: www-data}

  dns-server:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
    features: {bind-dns: dns}
    services: [{port: 53, protocol: udp, name: dns}]
    roles: {dns: named}

  hmi-server:
    type: compute
    os: windows
    os_distribution: windows-server
    os_version: "2008 R2"
    resources: {ram: 2 gib, cpu: 1}
    description: "SCADA Human-Machine Interface"
    features: {scada-hmi: operator}
    services: [{port: 502, name: modbus}, {port: 3389, name: rdp}]
    roles: {operator: scada-op}
    asset_value: {integrity: critical, availability: critical}

  plc-power:
    type: compute
    os: other
    resources: {ram: 256 mib, cpu: 1}
    description: "Power grid PLC controller"
    services: [{port: 102, name: s7comm}]
    asset_value: {integrity: critical, availability: critical}

  plc-water:
    type: compute
    os: other
    resources: {ram: 256 mib, cpu: 1}
    description: "Water treatment PLC controller"
    services: [{port: 102, name: s7comm}]
    asset_value: {integrity: critical, availability: critical}

infrastructure:
  dmz-net: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  it-net: {count: 1, properties: {cidr: 10.0.1.0/24, gateway: 10.0.1.1, internal: true}}
  ot-net: {count: 1, properties: {cidr: 10.0.2.0/24, gateway: 10.0.2.1, internal: true}}
  scada-net:
    count: 1
    properties: {cidr: 10.0.3.0/24, gateway: 10.0.3.1, internal: true}
    acls:
      - {direction: in, from_net: it-net, action: deny}
      - {direction: in, from_net: ot-net, protocol: tcp, ports: [502, 102], action: allow}
  ad-dc: {count: 1, links: [it-net]}
  mail-server: {count: 1, links: [dmz-net, it-net]}
  web-portal: {count: 1, links: [dmz-net]}
  dns-server: {count: 1, links: [dmz-net, it-net]}
  hmi-server: {count: 1, links: [ot-net, scada-net]}
  plc-power: {count: 1, links: [scada-net]}
  plc-water: {count: 1, links: [scada-net]}

features:
  ad-berylia: {type: Service, source: adds-2022}
  postfix-mail: {type: Service, source: postfix-3}
  gov-website: {type: Service, source: wordpress}
  bind-dns: {type: Service, source: bind9}
  scada-hmi: {type: Service, source: wincc-hmi}

relationships:
  hmi-controls-power:
    type: manages
    source: scada-hmi
    target: plc-power
    properties: {protocol: s7comm}
  hmi-controls-water:
    type: manages
    source: scada-hmi
    target: plc-water
    properties: {protocol: modbus}
  mail-auth:
    type: authenticates_with
    source: postfix-mail
    target: ad-berylia

entities:
  berylia-blue:
    name: Berylia National CERT
    role: Blue
    mission: "Defend national IT/OT infrastructure"
    entities:
      it-team: {name: IT Security}
      ot-team: {name: OT/SCADA Security}
  crimsonia-red:
    name: "Crimsonia APT"
    role: Red
    mission: "Disrupt Berylia critical infrastructure"

conditions:
  scada-hmi-responsive:
    proposition: scada-hmi-responsive
    command: /usr/bin/check-hmi-availability
    interval: 60
  scada-hmi-disrupted:
    proposition: scada-hmi-disrupted
    command: /usr/bin/check-hmi-disruption
    interval: 60

evidence_requirements:
  scada-state-evidence:
    description: Capture governed HMI state observations.
    source_refs: [nodes.hmi-server]
    scope_refs: [nodes.hmi-server]
    boundary_kind: assertion_evaluation
    channel: log
    artifact_role: proposition_truth_evidence
    sensitivity: plain
    redaction: redact_secrets
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required

propositions:
  scada-hmi-responsive:
    description: The governed SCADA HMI is responsive.
    subjects: [nodes.hmi-server]
    basis: observed_state
    predicate: {kind: boolean, property: hmi-responsive, semantic_ref: urn:raes:observable:hmi-responsive, operator: equals, expected: true}
    evidence_requirements: [scada-state-evidence]
  scada-hmi-disrupted:
    description: The governed SCADA HMI is disrupted.
    subjects: [nodes.hmi-server]
    basis: observed_state
    predicate: {kind: boolean, property: hmi-disrupted, semantic_ref: urn:raes:observable:hmi-disrupted, operator: equals, expected: true}
    evidence_requirements: [scada-state-evidence]

assertions:
  scada-hmi-responsive: {proposition: scada-hmi-responsive, role: postcondition, polarity: positive}
  scada-hmi-disrupted: {proposition: scada-hmi-disrupted, role: postcondition, polarity: positive}

events:
  disruption-wave: {}
  recovery-phase: {}

scripts:
  locked-shields-day-1:
    start_time: 0
    end_time: 8 hour
    speed: 1
    events:
      disruption-wave: 2 hour
      recovery-phase: 4 hour

stories:
  main-exercise:
    scripts: [locked-shields-day-1]

objectives:
  crimsonia-disrupt-scada:
    entity: crimsonia-red
    targets: [hmi-controls-power, hmi-controls-water, hmi-server]
    success:
      assertions: [scada-hmi-disrupted]
    window:
      stories: [main-exercise]
      scripts: [locked-shields-day-1]
      events: [disruption-wave]

  berylia-maintain-operations:
    entity: berylia-blue.ot-team
    targets: [hmi-server, plc-power, plc-water]
    success:
      assertions: [scada-hmi-responsive]
    window:
      stories: [main-exercise]
      scripts: [locked-shields-day-1]
      events: [recovery-phase]
    depends_on: [crimsonia-disrupt-scada]
"""


# =======================================================================
# Test execution
# =======================================================================

SCENARIOS = [
    ("14. Incalmo Equifax breach", INCALMO_EQUIFAX),
    ("15. NICE Challenge 17", NICE_CHALLENGE_17),
    ("16. CCDC 2007 Burnsodyne", CCDC_BURNSODYNE),
    ("17. HTB Offshore-style AD", HTB_OFFSHORE),
    ("18. Metasploitable 2", METASPLOITABLE_2),
    ("19. Locked Shields IT/OT/SCADA", LOCKED_SHIELDS_STYLE),
]


@pytest.mark.parametrize("label,yaml_str", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_parses_and_validates(label, yaml_str):
    """Each real-world scenario must parse and pass semantic validation."""
    scenario, error = _parse(yaml_str, label)
    assert error is None, f"{label} failed: {error}"
    assert scenario is not None


@pytest.mark.parametrize("label,yaml_str", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_topology_integrity(label, yaml_str):
    """Infrastructure references and cross-references are consistent."""
    scenario = parse_sdl(textwrap.dedent(yaml_str))
    for name in scenario.infrastructure:
        assert name in scenario.nodes, f"{label}: infra '{name}' missing node"
    for node_name, node in scenario.nodes.items():
        for feat_name in node.features:
            assert feat_name in scenario.features, f"{label}: node '{node_name}' refs missing feature '{feat_name}'"


@pytest.mark.parametrize("label,yaml_str", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_stats(label, yaml_str):
    """Every real-world scenario must present a non-trivial topology.

    Each computed metric is exercised by an assertion so a regression that
    silently drops a scenario's hosts, networks, feature bindings, or overall
    richness is caught, rather than leaving dead metric variables (mirrors the
    content-presence checks in test_sdl_stress.py::test_scenario_parses_and_validates).
    """
    scenario = parse_sdl(textwrap.dedent(yaml_str))
    nodes = len([n for n in scenario.nodes.values() if n.type.value == "compute"])
    nets = len([n for n in scenario.nodes.values() if n.type.value == "switch"])
    features = len(scenario.features)
    accts = len(scenario.accounts)
    rels = len(scenario.relationships)

    # Every study scenario is a multi-host, networked topology with service
    # feature bindings, so these lower bounds hold for the whole parametrized set.
    assert nodes >= 1, f"{label}: no compute nodes"
    assert nets >= 1, f"{label}: no networks"
    assert features >= 1, f"{label}: no feature bindings"

    # Accounts and relationships are legitimately absent from
    # some fixtures (e.g. the CCDC defense scenario models none), so they are
    # folded into an overall richness floor instead of each asserted >= 1.
    total_elements = nodes + nets + features + accts + rels
    assert total_elements >= 10, f"{label}: scenario too sparse ({total_elements} elements)"


def test_objectives_are_exercised_in_realworld_suite():
    """At least one real-world fixture should carry declarative objectives."""
    labels_with_objectives: list[str] = []
    for label, yaml_str in SCENARIOS:
        scenario = parse_sdl(textwrap.dedent(yaml_str))
        if scenario.objectives:
            labels_with_objectives.append(label)

    assert labels_with_objectives
