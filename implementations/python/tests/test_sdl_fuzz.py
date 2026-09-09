"""Property-based fuzz testing for the SDL parser and validator.

Uses Hypothesis to generate random SDL-like YAML structures and verify
that the parser never crashes — it either produces a valid Scenario or
raises a clean SDLParseError/SDLValidationError. No unhandled exceptions.

Run manually (not included in standard test suite):
    pytest tests/test_sdl_fuzz.py -v --timeout=300

Requires: pip install hypothesis
"""

import string

import pytest
import yaml
from hypothesis import HealthCheck, assume, example, given, settings
from hypothesis import strategies as st
from raes import SDLParseError, SDLValidationError, parse_sdl
from raes.scenario import Scenario

# Mark entire module so it's excluded from default test runs.
# Run with: pytest tests/test_sdl_fuzz.py -v
pytestmark = pytest.mark.fuzz


# ---------------------------------------------------------------------------
# Strategies: building blocks for generating SDL-like data
# ---------------------------------------------------------------------------

# Identifiers (node names, feature names, etc.)
slugs = st.from_regex(r"[a-z][a-z0-9\-]{0,20}", fullmatch=True)

# Small positive integers
small_ints = st.integers(min_value=1, max_value=100)

# RAM strings
ram_values = st.sampled_from(["256 mib", "512 mib", "1 gib", "2 gib", "4 gib", "8 gib"])

# OS families
os_families = st.sampled_from(["windows", "linux", "macos", "freebsd", "other"])

# Node types
node_types = st.sampled_from(["compute", "switch"])

# Feature types
feature_types = st.sampled_from(["service", "configuration", "artifact"])

# CWE classes
cwe_classes = st.from_regex(r"CWE-[1-9][0-9]{0,3}", fullmatch=True)

# Ports
ports = st.integers(min_value=1, max_value=65535)

# Password strengths
password_strengths = st.sampled_from(["weak", "medium", "strong", "none"])

# Relationship types
relationship_types = st.sampled_from(
    [
        "authenticates_with",
        "trusts",
        "federates_with",
        "connects_to",
        "depends_on",
        "manages",
        "replicates_to",
    ]
)

# Variable types
variable_types = st.sampled_from(["string", "integer", "boolean", "number"])

# Exercise roles
exercise_roles = st.sampled_from(["white", "green", "red", "blue"])

# Metric types
metric_types = st.sampled_from(["manual", "conditional"])


# ---------------------------------------------------------------------------
# Composite strategies: generating valid-ish SDL sections
# ---------------------------------------------------------------------------


@st.composite
def vm_nodes(draw):
    """Generate a dict of compute nodes."""
    n = draw(st.integers(min_value=1, max_value=5))
    nodes = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in nodes)
        nodes[name] = {
            "type": "compute",
            "os": draw(os_families),
            "resources": {"ram": draw(ram_values), "cpu": draw(small_ints)},
        }
    return nodes


@st.composite
def switch_nodes(draw):
    """Generate a dict of switch nodes."""
    n = draw(st.integers(min_value=1, max_value=3))
    nodes = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in nodes)
        nodes[name] = {"type": "switch"}
    return nodes


@st.composite
def features_section(draw):
    """Generate a dict of features."""
    n = draw(st.integers(min_value=0, max_value=5))
    features = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in features)
        features[name] = {
            "type": draw(feature_types),
            "source": draw(slugs),
        }
    return features


@st.composite
def vulnerabilities_section(draw):
    """Generate a dict of vulnerabilities."""
    n = draw(st.integers(min_value=0, max_value=5))
    vulns = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in vulns)
        vulns[name] = {
            "name": draw(st.text(min_size=1, max_size=30, alphabet=string.ascii_letters + " ")),
            "description": draw(st.text(min_size=1, max_size=50, alphabet=string.ascii_letters + " ")),
            "technical": draw(st.booleans()),
            "class": draw(cwe_classes),
        }
    return vulns


@st.composite
def accounts_section(draw, node_names):
    """Generate accounts referencing existing nodes."""
    if not node_names:
        return {}
    n = draw(st.integers(min_value=0, max_value=5))
    accounts = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in accounts)
        accounts[name] = {
            "username": draw(slugs),
            "node": draw(st.sampled_from(list(node_names))),
            "password_strength": draw(password_strengths),
        }
    return accounts


@st.composite
def relationships_section(draw, all_names):
    """Generate relationships referencing existing elements."""
    if len(all_names) < 2:
        return {}
    names_list = list(all_names)
    n = draw(st.integers(min_value=0, max_value=4))
    rels = {}
    for _ in range(n):
        name = draw(slugs)
        assume(name not in rels)
        rels[name] = {
            "type": draw(relationship_types),
            "source": draw(st.sampled_from(names_list)),
            "target": draw(st.sampled_from(names_list)),
        }
    return rels


@st.composite
def valid_sdl_scenario(draw):
    """Generate a structurally plausible SDL scenario."""
    vms = draw(vm_nodes())
    switches = draw(switch_nodes())

    all_nodes = {**switches, **vms}
    node_names = set(all_nodes.keys())
    vm_names = set(vms.keys())

    feats = draw(features_section())

    # Build infrastructure
    infra = {}
    for sw_name in switches:
        infra[sw_name] = {
            "count": 1,
            "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"},
        }
    switch_names = list(switches.keys())
    for vm_name in vms:
        entry = {"count": 1}
        if switch_names:
            entry["links"] = [draw(st.sampled_from(switch_names))]
        infra[vm_name] = entry

    # Build accounts referencing vm nodes
    accts = draw(accounts_section(vm_names))

    # Collect all named elements for relationships
    all_names = set()
    all_names.update(node_names)
    all_names.update(feats.keys())
    all_names.update(accts.keys())

    rels = draw(relationships_section(all_names))

    scenario = {
        "name": draw(slugs),
        "nodes": all_nodes,
        "infrastructure": infra,
    }
    if feats:
        scenario["features"] = feats
    if accts:
        scenario["accounts"] = accts
    if rels:
        scenario["relationships"] = rels

    return scenario


# ---------------------------------------------------------------------------
# Fuzz tests
# ---------------------------------------------------------------------------


@given(data=valid_sdl_scenario())
@settings(
    max_examples=200,
    deadline=5000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_valid_sdl_never_crashes(data):
    """Generated SDL-like structures must parse cleanly or raise clean errors.

    The parser must NEVER raise an unhandled exception (TypeError,
    KeyError, AttributeError, etc.). Only SDLParseError or
    SDLValidationError are acceptable failures.
    """
    yaml_str = yaml.dump(data, default_flow_style=False)
    # Structural preservation is unconditional, even if semantic references fail.
    structural = parse_sdl(yaml_str, skip_semantic_validation=True)
    assert structural.name == data["name"]
    assert set(structural.nodes) == set(data["nodes"])
    for name, node in data["nodes"].items():
        assert structural.nodes[name].type.value == node["type"]
        if node["type"] == "compute":
            assert structural.nodes[name].resources.cpu == node["resources"]["cpu"]
            assert structural.nodes[name].os.value == node["os"]
    assert set(structural.features) == set(data.get("features", {}))
    assert set(structural.accounts) == set(data.get("accounts", {}))
    try:
        scenario = parse_sdl(yaml_str)
    except SDLValidationError as exc:
        assert exc.errors
    else:
        assert scenario.model_dump(mode="json") == structural.model_dump(mode="json")


@given(raw=st.text(min_size=0, max_size=500))
@example(raw="name: arbitrary-success\nnodes: {sw: {type: switch}}\n")
@example(raw="name: yes\nnodes: {sw: {type: switch}}\n")
@settings(
    max_examples=500,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_arbitrary_text_never_crashes(raw):
    """Completely random text must never cause an unhandled crash."""
    try:
        scenario = parse_sdl(raw)
    except (SDLParseError, SDLValidationError) as exc:
        assert str(exc)
    else:
        assert isinstance(scenario, Scenario)
        payload = scenario.model_dump(mode="json", exclude_defaults=True)
        assert parse_sdl(yaml.safe_dump(payload)).model_dump(mode="json") == scenario.model_dump(mode="json")
        source = yaml.compose(raw, Loader=yaml.SafeLoader)
        assert isinstance(source, yaml.MappingNode)
        assert scenario.name == next(value.value for key, value in source.value if key.value == "name")


@given(
    data=st.fixed_dictionaries(
        {
            "name": slugs,
        }
    ).flatmap(
        lambda base: st.fixed_dictionaries(
            {
                **{k: st.just(v) for k, v in base.items()},
                "extra_field": slugs,
            }
        )
    )
)
@settings(max_examples=50, deadline=2000)
def test_extra_fields_rejected_cleanly(data):
    """Scenarios with unknown top-level fields raise clean errors."""
    yaml_str = yaml.dump(data, default_flow_style=False)
    with pytest.raises(SDLParseError, match="Extra inputs are not permitted") as excinfo:
        parse_sdl(yaml_str)
    assert any(d.code == "sdl.model.invalid" and d.pointer == "/extra_field" for d in excinfo.value.diagnostics)


@given(
    nodes=st.dictionaries(
        slugs,
        st.fixed_dictionaries(
            {
                "type": st.just("compute"),
                "resources": st.fixed_dictionaries(
                    {
                        "ram": ram_values,
                        "cpu": small_ints,
                    }
                ),
                "services": st.lists(
                    st.fixed_dictionaries(
                        {
                            "port": st.integers(min_value=-1, max_value=65536),
                            "protocol": st.sampled_from(["tcp", "udp"]),
                            "name": slugs,
                        }
                    ),
                    min_size=0,
                    max_size=10,
                    unique_by=(lambda service: (service["port"], service["protocol"]), lambda service: service["name"]),
                ),
            }
        ),
        min_size=1,
        max_size=5,
    )
)
@settings(
    max_examples=100,
    deadline=3000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fuzz_service_ports(nodes):
    """Service ports preserve valid values and reject values outside 1..65535."""
    data = {"name": "fuzz-services", "nodes": nodes}
    yaml_str = yaml.dump(data, default_flow_style=False)
    invalid = [
        (name, i)
        for name, node in nodes.items()
        for i, service in enumerate(node["services"])
        if not 1 <= service["port"] <= 65535
    ]
    if invalid:
        with pytest.raises(SDLParseError, match="port must be") as excinfo:
            parse_sdl(yaml_str)
        pointers = {d.pointer for d in excinfo.value.diagnostics if d.code == "sdl.model.invalid"}
        assert all(f"/nodes/{name}/services/{i}/port" in pointers for name, i in invalid)
    else:
        scenario = parse_sdl(yaml_str, skip_semantic_validation=True)
        for name, node in nodes.items():
            assert [(s.port, s.protocol, s.name) for s in scenario.nodes[name].services] == [
                (s["port"], s["protocol"], s["name"]) for s in node["services"]
            ]


@given(
    vulns=st.dictionaries(
        slugs,
        st.fixed_dictionaries(
            {
                "name": st.text(min_size=1, max_size=20, alphabet=string.ascii_letters),
                "description": st.text(min_size=1, max_size=30, alphabet=string.ascii_letters),
                "technical": st.booleans(),
                "class": st.text(min_size=1, max_size=15),  # intentionally sometimes invalid
            }
        ),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=100, deadline=2000)
def test_fuzz_vulnerability_class_validation(vulns):
    """Historical declarations require migration regardless of the CWE spelling."""
    data = {"name": "fuzz-vulns", "nodes": {"sw": {"type": "switch"}}, "vulnerabilities": vulns}
    yaml_str = yaml.dump(data, default_flow_style=False)
    with pytest.raises(SDLParseError, match="classification migration"):
        parse_sdl(yaml_str)


@given(
    names=st.lists(slugs, min_size=2, max_size=6, unique=True),
    cyclic=st.booleans(),
)
@settings(
    max_examples=100,
    deadline=3000,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fuzz_feature_dependency_cycles(names, cyclic):
    """Reject generated cycles and preserve generated acyclic chains."""
    features = {name: {"type": "service", "dependencies": names[i + 1 : i + 2]} for i, name in enumerate(names)}
    if cyclic:
        features[names[-1]]["dependencies"] = [names[0]]
    data = {"name": "fuzz-deps", "features": features}
    yaml_str = yaml.dump(data, default_flow_style=False)
    if cyclic:
        with pytest.raises(SDLValidationError, match="Feature dependency graph contains a cycle"):
            parse_sdl(yaml_str)
    else:
        scenario = parse_sdl(yaml_str)
        assert {name: f.dependencies for name, f in scenario.features.items()} == {
            name: f["dependencies"] for name, f in features.items()
        }


@given(
    pair=st.sampled_from(
        [
            ("Password-Strength", "password_strength"),
            ("PASSWORD_STRENGTH", "password-strength"),
            ("password-strength", "Password_Strength"),
        ]
    )
)
@settings(max_examples=50, deadline=2000)
def test_fuzz_structural_key_alias_mutations_fail_closed(pair):
    """Generated field aliases must never overwrite an earlier spelling."""
    first, second = pair
    source = f"""\
name: fuzz-aliases
nodes:
  host: {{type: switch}}
accounts:
  alice:
    username: alice
    node: host
    {first}: strong
    {second}: weak
"""

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(source)
    assert excinfo.value.diagnostics[0].code == "sdl.mapping_key_conflict"


@given(identifier=slugs)
@settings(max_examples=50, deadline=2000)
def test_fuzz_exact_identifier_duplicate_mutations_fail_closed(identifier):
    """Generated duplicate symbol definitions must fail before construction."""
    source = f"""\
name: fuzz-duplicates
nodes:
  {identifier}: {{type: switch}}
  {identifier}: {{type: switch}}
"""

    with pytest.raises(SDLParseError) as excinfo:
        parse_sdl(source)
    assert excinfo.value.diagnostics[0].code == "sdl.mapping_key_conflict"
