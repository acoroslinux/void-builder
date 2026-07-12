import os
import shutil
from void_builder.core.base_module import BaseModule

class CleanupModule(BaseModule):
    def __init__(self, config):
        super().__init__(config)
        self.output_dir = self.config.get('output_dir', './output')
        self.iso_dir = f"{self.output_dir}_iso"
        self.cleanup = self.config.get('cleanup', True)

    def run(self):
        if not self.cleanup:
            print("Cleanup disabled in config. Skipping.")
            return

        print("Cleaning up temporary directories...")
        
        try:
            if os.path.exists(self.output_dir):
                print(f"Removing {self.output_dir}...")
                shutil.rmtree(self.output_dir)
                
            if os.path.exists(self.iso_dir):
                print(f"Removing {self.iso_dir}...")
                shutil.rmtree(self.iso_dir)
                
            print("Cleanup complete.")
        except Exception as e:
            print(f"Failed to cleanup: {e}")
