# BMC-user-creation

This is a script that takes in a user-provided YAML file that contains BMC information and creates users on each given BMC.

Usage:

1. Install dependencies:
    * `pip install -r requirements.txt`
2. Create YAML file formatted in the same manner as `example.yml`
3. Run Script:
    * `python3 user_creation.py -i example.yml`