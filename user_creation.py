# TODO: take in yaml of IP's and creds, and new user/pass
# TODO: check if all creds present
# TODO: go thru existing accounts and check if username glpi exists at redfish/v1/AccountService/Accounts/ ['UserName']
# TODO: if not, create one
import urllib3
import argparse
import yaml
import redfish

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main() -> None:
    """Main function"""
    # Get the command line arguments from the user.
    parser = argparse.ArgumentParser(description="Create new BMC Users")
    parser.add_argument(
        "-i",
        "--info",
        metavar="info",
        help="path to credential YAML file",
        required=True,
    )
    args = parser.parse_args()
    info_path = args.info
    with open(info_path, "r") as info_path:
        info_dict = yaml.safe_load(info_path)
    print(info_dict)

    for machine in info_dict:
        key_list = list(info_dict[machine].keys())
        if (
            "admin_user" not in key_list
            or "admin_password" not in key_list
            or "new_user" not in key_list
            or "new_password" not in key_list
        ):
            raise Exception(
                "The YAML for "
                + machine
                + " is formatted incorrectly. Each machine should include the 'admin_user', 'admin_password', "
                + "'new_user', and 'new_password' subfields, as shown in example.yml"
            )
        base_url = "https://" + machine
        REDFISH_OBJ = redfish.redfish_client(
            base_url=base_url,
            username=info_dict[machine]['admin_user'],
            password=info_dict[machine]['admin_password'],
            default_prefix="/redfish/v1",
        )
        REDFISH_OBJ.login(auth="session")
        print(base_url)
        print(REDFISH_OBJ.get("/redfish/v1/Systems"))
# Executes main if run as a script.
if __name__ == "__main__":
    main()
