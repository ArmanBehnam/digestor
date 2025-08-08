import yaml

class ConfigLoader:
    @staticmethod
    def load(config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)