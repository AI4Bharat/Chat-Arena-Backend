"""
Configuration entities for synthetic ASR dataset generation.
Ported from synthetic-benchmarks/models/entities.py for Django integration.
DO NOT MODIFY EXISTING synthetic_asr MODULES WHEN USING THIS FILE.
"""

from typing import NamedTuple, List, Tuple, Dict


class SentenceGeneratorConfig(NamedTuple):
    """Configuration for sentence generation phase"""
    category: str
    style: List[str]
    description: str
    entities: List[str]
    topic_persona_instruction: str
    sub_domain_instruction: str
    scenario_instruction: str

    def __str__(self):
        return f"SentenceGeneratorConfig -> category: {self.category}, style: {self.style}, " \
               f"description: {self.description}, entities: {self.entities}, " \
               f"topic_persona: {self.topic_persona_instruction}, " \
               f"sub_domain: {self.sub_domain_instruction}, " \
               f"scenario: {self.scenario_instruction}"

    def get_dict(self):
        return {
            "category": self.category,
            "style": self.style,
            "description": self.description,
            "entities": self.entities,
            "topic_persona_instruction": self.topic_persona_instruction,
            "sub_domain_instruction": self.sub_domain_instruction,
            "scenario_instruction": self.scenario_instruction,
        }

    @classmethod
    def create_obj_from_dict(cls, dict_obj: Dict) -> Tuple['SentenceGeneratorConfig | None', Dict[str, str]]:
        """Create from dict with validation"""
        issues = {}
        has_issue = False
        
        category = dict_obj.get("category", "")
        if not category:
            issues["category"] = "Missing"
            has_issue = True

        style = dict_obj.get("style", [])
        if not style:
            style = ["Conversational"]  # Default style

        description = dict_obj.get("description", "")

        # Parse entities
        entities_str = dict_obj.get("entities", None)
        entities = []
        if entities_str:
            if isinstance(entities_str, list):
                entities = entities_str
            elif isinstance(entities_str, str):
                entities = [e.strip() for e in entities_str.split(",") if e.strip()]

        topic_persona_instruction = dict_obj.get("topic_persona_instruction", "")
        sub_domain_instruction = dict_obj.get("sub_domain_instruction", "")
        scenario_instruction = dict_obj.get("scenario_instruction", "")

        if has_issue:
            return None, issues

        config = cls(
            category=category,
            style=style,
            description=description,
            entities=entities,
            topic_persona_instruction=topic_persona_instruction,
            sub_domain_instruction=sub_domain_instruction,
            scenario_instruction=scenario_instruction,
        )

        return config, {}


class AudioGeneratorConfig(NamedTuple):
    """Configuration for audio generation phase"""
    age_group: List[str]
    gender: List[str]
    accent: List[str]

    def __str__(self):
        return f"AudioGeneratorConfig -> age_group: {self.age_group}, " \
               f"gender: {self.gender}, accent: {self.accent}"

    def get_dict(self):
        return {
            "age_group": self.age_group,
            "gender": self.gender,
            "accent": self.accent,
        }

    @classmethod
    def create_obj_from_dict(cls, dict_obj: Dict) -> Tuple['AudioGeneratorConfig | None', Dict[str, str]]:
        """Create from dict with validation"""
        issues = {}

        age_group = dict_obj.get("age_group", None)
        if not age_group:
            issues["age_group"] = "Age group is not mentioned"
            age_group = []
        elif not isinstance(age_group, list):
            issues["age_group"] = "Age group should be a list of values"
            age_group = []
        else:
            age_group = list(age_group)

        gender = dict_obj.get("gender", None)
        if not gender:
            issues["gender"] = "Gender is not mentioned"
            gender = []
        elif not isinstance(gender, list):
            issues["gender"] = "Gender should be a list of values"
            gender = []
        else:
            gender = list(gender)

        accent = dict_obj.get("accent", None)
        if not accent:
            accent = ["normal"]
        elif not isinstance(accent, list):
            accent = [accent]
        else:
            accent = list(accent)

        config = cls(age_group=age_group, gender=gender, accent=accent)
        return config, issues


class Config(NamedTuple):
    """Main dataset configuration combining sentence and audio configs"""
    job_id: str
    language: str
    size: int
    sentence_config: SentenceGeneratorConfig
    audio_config: AudioGeneratorConfig

    def __str__(self):
        return f"Config -> job_id: {self.job_id}, language: {self.language}, " \
               f"size: {self.size}, {self.sentence_config}, {self.audio_config}"

    def get_dict(self):
        return {
            "job_id": self.job_id,
            "language": self.language,
            "size": self.size,
            "sentence_config": self.sentence_config.get_dict(),
            "audio_config": self.audio_config.get_dict(),
        }

    @classmethod
    def create_obj_from_dict(cls, dict_obj: Dict, require_audio_config: bool = False) -> Tuple['Config | None', Dict[str, str]]:
        """Create from dict with validation"""
        issues = {}

        job_id = str(dict_obj.get("job_id", ""))
        if not job_id:
            issues["job_id"] = "Job ID is missing"

        language = dict_obj.get("language", "hindi")

        try:
            size = int(dict_obj.get("size", 1))
            if size < 1:
                size = 1
        except (ValueError, TypeError):
            size = 1

        # Parse sentence config
        sentence_dict = dict_obj.get("sentence", {})
        sentence_config, sentence_issues = SentenceGeneratorConfig.create_obj_from_dict(sentence_dict)
        if sentence_issues:
            issues.update(sentence_issues)

        if not sentence_config:
            return None, issues

        # Parse audio config (optional or required)
        audio_config = None
        audio_dict = dict_obj.get("audio", {})
        
        if require_audio_config or audio_dict:
            audio_config, audio_issues = AudioGeneratorConfig.create_obj_from_dict(audio_dict)
            if audio_issues and require_audio_config:
                issues.update(audio_issues)

        config = cls(
            job_id=job_id,
            language=language,
            size=size,
            sentence_config=sentence_config,
            audio_config=audio_config,
        )

        return config, issues
