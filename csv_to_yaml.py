"""Script that generates a YAML file from a CSV file for use with user_creation.py"""
import argparse
import csv

import yaml


def csv_to_yaml(csv_file, yaml_file, new_user, new_password):
    """Converts csv to yaml

    Args:
        csv_file (string): path to CSV file
        yaml_file (string): path to YAML file
        new_user (string): username for new account
        new_password (string): password for new account
    """
    data = {}

    with open(csv_file, "r", encoding="utf-8") as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            ip_address = row[0]
            admin_user = row[1]
            admin_password = row[2]
            data[ip_address] = {
                "admin_user": admin_user,
                "admin_password": admin_password,
                "new_user": new_user,
                "new_password": new_password,
            }

    with open(yaml_file, "w", encoding="utf-8") as yamlfile:
        yaml.dump(data, yamlfile, default_flow_style=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create new BMC Users")
    parser.add_argument(
        "-c",
        "--csv",
        metavar="csv",
        help="path to CSV file",
        required=True,
    )
    parser.add_argument(
        "-y",
        "--yaml",
        metavar="yaml",
        help="path to YAML file",
        required=True,
    )
    parser.add_argument(
        "-u",
        "--user",
        metavar="user",
        help="new user name",
        required=True,
    )
    parser.add_argument(
        "-p",
        "--password",
        metavar="password",
        help="new user password",
        required=True,
    )
    args = parser.parse_args()

    csv_to_yaml(args.csv, args.yaml, args.user, args.password)
