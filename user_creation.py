#TODO: take in yaml of IP's and creds, and new user/pass
#TODO: check if all creds present
#TODO: go thru existing accounts and check if username glpi exists at redfish/v1/AccountService/Accounts/ ['UserName']
#TODO: if not, create one
import urllib3
import argparse
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main() -> None:
    """Main function"""
    # Get the command line arguments from the user.
    parser = argparse.ArgumentParser(
        description="Create new BMC Users"
    )
    parser.add_argument(
        "-i",
        "--info",
        metavar="info",
        help="path to credential YAML file",
        required=True
    )
    args = parser.parse_args()
    info_path = args.info
    with open(info_path, "r") as info_path:
        info_dict = yaml.safe_load(info_path)
    print(info_dict)

# Executes main if run as a script.
if __name__ == "__main__":
    main()