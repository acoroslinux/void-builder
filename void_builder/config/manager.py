import yaml
import json
import os

class ConfigManager:
    def __init__(self, config_path, common_dir=None):
        self.config_path = config_path
        self.common_dir = common_dir
        self.config = self._load_and_merge_config()

    def _load_file(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        
        _, ext = os.path.splitext(path)
        with open(path, 'r') as f:
            if ext.lower() in ['.yaml', '.yml']:
                return yaml.safe_load(f) or {}
            elif ext.lower() == '.json':
                return json.load(f) or {}
            else:
                raise ValueError(f"Unsupported config format: {ext}")

    def _merge_dicts(self, dict1, dict2):
        """Recursively merges dict2 into dict1."""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                # For lists, we append unique items
                for item in value:
                    if item not in result[key]:
                        result[key].append(item)
            else:
                result[key] = value
        return result

    def _load_and_merge_config(self):
        # Load the specific build config
        build_config = self._load_file(self.config_path)
        
        # If no common_dir is provided, try to infer it from the config path
        # Assuming structure: configs/builds/my_build.yaml -> configs/common/
        if not self.common_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(self.config_path)))
            potential_common_dir = os.path.join(base_dir, 'common')
            if os.path.exists(potential_common_dir):
                self.common_dir = potential_common_dir

        merged_config = {}
        
        # Load and merge all common configs if the directory exists
        if self.common_dir and os.path.exists(self.common_dir):
            for filename in sorted(os.listdir(self.common_dir)):
                if filename.endswith(('.yaml', '.yml', '.json')):
                    common_path = os.path.join(self.common_dir, filename)
                    common_config = self._load_file(common_path)
                    merged_config = self._merge_dicts(merged_config, common_config)
                    
        # Finally, merge the specific build config (it overrides common settings)
        merged_config = self._merge_dicts(merged_config, build_config)
        
        return merged_config

    def get(self, key, default=None):
        return self.config.get(key, default)
