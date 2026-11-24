package governance

const (
	attackVocabularyCheck     = "attack-tactic-vocabulary"
	atlasVocabularyCheck      = "atlas-tactic-vocabulary"
	nistVocabularyCheck       = "nist-csf-defensive-vocabulary"
	autonomousVocabularyCheck = "autonomous-behavior-vocabularies"
	nistVocabulary            = "NIST"
	fipaVocabulary            = "FIPA"
	sourceAuthorityField      = "source_authority"
	sourceVersionField        = "source_version"
	sourceURLField            = "source_url"
	sourceDigestField         = "source_digest"
	licenseURLField           = "license_url"
	licenseNoticeField        = "license_notice"
	descriptionField          = "description"
	fipaSpecificationURL      = "https://www.fipa.org/specs/fipa00037/SC00037J.html"
)

func vocabularyProfiles(tool string) []vocabularyProfile {
	switch tool {
	case attackVocabularyCheck:
		return []vocabularyProfile{
			{path: "contracts/concept-authority/attack-enterprise-tactics-source-v1.json", label: attackVocabulary, id: "participant-offensive-behavior-activities", fields: []vocabularyField{
				{sourceAuthorityField, "MITRE ATT&CK"},
				{"source_domain", "enterprise-attack"},
				{sourceVersionField, "v19.1"},
				{sourceURLField, "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/v19.1/enterprise-attack/enterprise-attack-19.1.json"},
				{sourceDigestField, "sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3"},
				{licenseURLField, "https://attack.mitre.org/resources/legal-and-branding/terms-of-use/"},
				{licenseNoticeField, "© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation."},
			}, citations: []vocabularyCitation{
				{"https://raw.githubusercontent.com/mitre-attack/attack-stix-data/v19.1/enterprise-attack/enterprise-attack-19.1.json", "citation_urls must include the pinned STIX bundle URL", "citation_urls omits STIX URL"},
				{"https://attack.mitre.org/resources/legal-and-branding/terms-of-use/", "citation_urls must include the MITRE terms URL", "citation_urls omits terms URL"},
			}},
		}
	case atlasVocabularyCheck:
		return []vocabularyProfile{
			{path: "contracts/concept-authority/atlas-tactics-source-v1.json", label: atlasVocabulary, id: "participant-ai-offensive-behavior-activities", fields: []vocabularyField{
				{sourceAuthorityField, "MITRE ATLAS"},
				{sourceVersionField, "2026.06"},
				{"source_format_version", "6.0.0"},
				{sourceURLField, "https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml"},
				{sourceDigestField, "sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a"},
				{licenseURLField, "https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE"},
				{licenseNoticeField, "Copyright 2021-2026 MITRE. Licensed under the Apache License, Version 2.0. Public Release Case Number 26-1162."},
				{"collection_id", "ATLAS-collection"},
				{"matrix_id", atlasMatrixID},
			}, citations: []vocabularyCitation{
				{"https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml", "citation_urls must include https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml", "citation_urls must include https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml"},
				{"https://github.com/mitre-atlas/atlas-data/releases/tag/v2026.06", "citation_urls must include https://github.com/mitre-atlas/atlas-data/releases/tag/v2026.06", "citation_urls must include https://github.com/mitre-atlas/atlas-data/releases/tag/v2026.06"},
				{"https://github.com/mitre-atlas/atlas-data/blob/main/README.md", "citation_urls must include https://github.com/mitre-atlas/atlas-data/blob/main/README.md", "citation_urls must include https://github.com/mitre-atlas/atlas-data/blob/main/README.md"},
				{"https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE", "citation_urls must include https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE", "citation_urls must include https://github.com/mitre-atlas/atlas-data/blob/main/LICENSE"},
				{"https://atlas.mitre.org/", "citation_urls must include https://atlas.mitre.org/", "citation_urls must include https://atlas.mitre.org/"},
			}},
		}
	case nistVocabularyCheck:
		return []vocabularyProfile{
			{path: "contracts/concept-authority/nist-csf-defensive-categories-source-v1.json", label: nistVocabulary, id: "participant-defensive-behavior-activities", fields: []vocabularyField{
				{sourceAuthorityField, "NIST Cybersecurity Framework"},
				{sourceVersionField, "2.0"},
				{sourceURLField, "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?"},
				{sourceDigestField, "sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3"},
				{licenseURLField, "https://www.nist.gov/copyrights-disclaimers"},
				{licenseNoticeField, "Adapted from NIST CSF 2.0. Except for material marked as copyrighted, NIST site information is public information that may be distributed or copied; appropriate source credit is requested."},
			}, citations: []vocabularyCitation{
				{"https://csrc.nist.gov/extensions/nudp/services/json/csf/download?", "citation_urls must include https://csrc.nist.gov/extensions/nudp/services/json/csf/download?", ""},
				{"https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20", "citation_urls must include https://www.nist.gov/publications/nist-cybersecurity-framework-csf-20", ""},
				{"https://doi.org/10.6028/NIST.CSWP.29", "citation_urls must include https://doi.org/10.6028/NIST.CSWP.29", ""},
				{"https://www.nist.gov/copyrights-disclaimers", "citation_urls must include https://www.nist.gov/copyrights-disclaimers", ""},
			}},
		}
	case autonomousVocabularyCheck:
		return []vocabularyProfile{
			{path: "contracts/concept-authority/w3c-activitystreams-activity-types-source-v1.json", label: activityVocabulary, id: "", fields: []vocabularyField{
				{sourceAuthorityField, "World Wide Web Consortium"},
				{sourceVersionField, "REC-activitystreams-vocabulary-20170523"},
				{"source_status", "W3C Recommendation"},
				{sourceURLField, "https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/"},
				{sourceDigestField, "sha256:1418443392160f4bb23dffb5727f5216d1f56d3430377dc67d364016521401db"},
				{licenseURLField, "https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document"},
				{licenseNoticeField, "Copyright © 2017 Activity Streams Working Group, IBM & SAP SE; W3C permissive document license applies."},
			}, citations: []vocabularyCitation{
				{"https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/", "citation_urls must include https://www.w3.org/TR/2017/REC-activitystreams-vocabulary-20170523/", ""},
				{"https://www.w3.org/TR/activitystreams-vocabulary/", "citation_urls must include https://www.w3.org/TR/activitystreams-vocabulary/", ""},
				{"https://www.w3.org/TR/2017/REC-activitystreams-core-20170523/", "citation_urls must include https://www.w3.org/TR/2017/REC-activitystreams-core-20170523/", ""},
				{"https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document", "citation_urls must include https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document", ""},
			}},
			{path: "contracts/concept-authority/fipa-communicative-acts-source-v1.json", label: fipaVocabulary, id: "", fields: []vocabularyField{
				{sourceAuthorityField, "Foundation for Intelligent Physical Agents"},
				{sourceVersionField, "SC00037J-2002-12-03"},
				{"source_status", "Standard"},
				{sourceURLField, fipaSpecificationURL},
				{"source_artifact_url", "https://www.fipa.org/specs/fipa00037/SC00037J.pdf"},
				{sourceDigestField, "sha256:90b3277247ef7e7f614ba4c0d58fb2b86aa53ff69036d27a731c09a26c605227"},
				{licenseURLField, fipaSpecificationURL},
				{licenseNoticeField, "Copyright © 1996-2002 Foundation for Intelligent Physical Agents. The specification notice grants no permission to use third-party intellectual property."},
			}, citations: []vocabularyCitation{
				{fipaSpecificationURL, "citation_urls must include https://www.fipa.org/specs/fipa00037/SC00037J.html", ""},
				{"https://www.fipa.org/specs/fipa00037/SC00037J.pdf", "citation_urls must include https://www.fipa.org/specs/fipa00037/SC00037J.pdf", ""},
				{"https://www.fipa.org/repository/aclspecs.html", "citation_urls must include https://www.fipa.org/repository/aclspecs.html", ""},
			}},
		}
	default:
		return nil
	}
}
