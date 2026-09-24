# -*- coding: utf-8 -*-
"""
Build docker container configuration files in batch.

"""

import os
import yaml
import json
import shutil
import copy
import pandas as pd

# Definition for our yaml dumper with customised representer
class QuotedString(str):
    pass

def quote_handler(dumper, data):
    """
    Handle the double quotes around json dicts in the yaml file.
    :param dumper:
    :param data:
    :return:
    """

    return dumper.represent_scalar(
        yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG,
        data,
        style="'"
    )

class YamlDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        # Forces the 4-space look for list items -> correct indent in yaml
        return super(YamlDumper, self).increase_indent(flow, False)

YamlDumper.add_representer(QuotedString, quote_handler)


class DockerComposeBuilder:
    """
    A new class for building docker-compose files in batch.
    This builder interprets the yaml file docker-compose.yaml with dict representation and make required node-wise
    modifications accordingly.
    """

    def __init__(self):
        # TODO: removed version and volumes, check if this fix the warnings.
        # Force quote version
        self.compose = {
            #'version': QuotedString(version),
            'networks': {},
            'services': {},
            #'volumes': {'sys': None, 'proc': None, 'etc': None}
        }

    def add_network(self, network_name):
        self.compose['networks'][f"{network_name}-proxy"] = {
            'external': {'name': network_name}
        }

    def bulk_add_services(self, services_dict):
        """
        Add service content blocks using default configurations.
        It is assumed that:
         - all containers running IEC 61850 applications use the default port 61850 internally.
         - the builder container uses local Dockerfile to perform the build process.
        """
        self.compose['services'].update(services_dict)

    def export_compose_file(self, file_path):
        with open(file_path, 'w') as f:
            yaml.dump(self.compose, f,
                      Dumper=YamlDumper,
                      sort_keys=False,
                      default_flow_style=False,
                      indent=2)


def update_node_configs(row, base_config, scl_source, secret_source, data_sources:dict, df_lookup_global):
    """
    This function extracts identical config and node-individual information, and make amendments in the yaml file
    accordingly.

    Note: data_sources is a list containing filepath of all data files in a group. Currently only this arg is a dict
    because each container may use a different data set for the simulation.

    :param row:
    :param base_config:
    :param scl_source:
    :param secret_source:
    :param data_sources:
    :param df_lookup_global:
    :return:
    """

    os.makedirs(row.node_path, exist_ok=True)

    node_cfg = copy.deepcopy(base_config)
    node_cfg['Container'].update({
        'container_name': row.service_name,
        'container_guid': row.guid,
        'service_name': row.service_name
    })
    # no matter what the SCL and original lookup files are named, just rename and pass the new filenames to config
    node_cfg['Interface']['path_scl'] = f"./settings/node{row.node_idx}.cid"
    node_cfg['Interface']['path_lookup'] = f"./settings/lookup.csv"

    with open(f"{row.node_path}/config.yaml", 'w') as f:
        yaml.dump(node_cfg, f, default_flow_style=False)

    df_node_lookup = df_lookup_global.copy()

    def update_json_guid(config_str):
        """
        Pre-processing logics for individual IED config, in particularly the data_source configuration.
        """

        if not isinstance(config_str, str): return config_str
        try:
            data = json.loads(config_str.replace("'", '"'))
            if 'guid' in data: data['guid'] = row.guid  # replace all guid appearences by the container guid
            if 'provider' in data: data['provider'] = os.path.basename(data_source)  # use hard-coded filename for data
            return json.dumps(data)
        except Exception as e:
            print(e)
            return config_str

    if 'fieldbus_conn_config' in df_node_lookup.columns:
        df_node_lookup['fieldbus_conn_config'] = df_node_lookup['fieldbus_conn_config'].apply(update_json_guid)

    df_node_lookup.to_csv(f"{row.node_path}/lookup.csv", index=False)
    shutil.copyfile(scl_source, f"{row.node_path}/node{row.node_idx}.cid")
    shutil.copyfile(secret_source, f"{row.node_path}/influxdb.json")
    data_source = data_sources.get(row.node_idx)
    if os.path.exists(data_source):
        shutil.copyfile(data_source, f"{row.node_path}/{os.path.basename(data_source)}")
    else:
        print(f'Data file does not exist: {data_source}')


def build_yaml_batch(path_mapping, path_config, path_lookup, path_scl, path_secret,
                     dir_output, name_image, group_network, max_apps, start_port):
    """
    Build docker-compose.yaml for all vIED containers. One application is considered the image builder, which can be
    used to create the docker image. All other containers rely on this prescribed image, there will be exactly one
    docker-compose file per group.

    NOTE: The docker-compose file for the builder might be faulty, you probably need to modify it by hand before
    putting it into the container platform. But this only has to be done once.

    :param path_mapping:
    :param path_config:
    :param path_lookup:
    :param path_scl:
    :param path_secret:
    :param dir_output:
    :param name_image:
    :param group_network:
    :param max_apps:
    :param start_port:
    :return:
    """
    df_mapping = pd.read_csv(path_mapping)
    df_lookup = pd.read_csv(path_lookup)
    with open(path_config, "r") as f:
        dict_config = yaml.safe_load(f)

    # init builder
    builder_dir = f"{dir_output}/builder"
    os.makedirs(builder_dir, exist_ok=True)
    builder_yaml = DockerComposeBuilder()
    builder_yaml.add_network(group_network)

    # add service block for image builder
    builder_yaml.bulk_add_services({
        f"{name_image}_builder": {
            'build': {'context': './', 'dockerfile': 'Dockerfile'},
            'image': f"{name_image}:1.0",
            'container_name': f"{name_image}_builder",
            'ports': [QuotedString("10000:61850")],
            'networks': [f"{group_network}-proxy"]
        }
    })
    builder_yaml.export_compose_file(f"{builder_dir}/docker-compose.yml")

    # Use data_mapping to extract node-wise specific configurations
    df = df_mapping.copy()
    df['node_idx'] = df.index
    df['service_name'] = df['node_idx'].apply(lambda i: f"{name_image}_node{i}")
    df['group_id'] = df['node_idx'] // max_apps
    df['group_dir'] = df['group_id'].apply(lambda g: f"{dir_output}/{name_image}_group{g}")
    df['node_path'] = df.apply(lambda r: f"{r.group_dir}/node{r.node_idx}", axis=1)

    # add service blocks per group for all nodes
    for g_idx, frame in df.groupby('group_id'):
        current_group_dir = frame['group_dir'].iloc[0]
        os.makedirs(current_group_dir, exist_ok=True)

        services_config = {}
        data_sources = {}
        for row in frame.itertuples():
            # TODO: here we use hard-coded file name for local time-series data, this means that we must replace the
            #  'provider' and 'field_key' entries in the lookup CSV accordingly. If multiple DAs in the virtual IED refer
            #  to this data file, we must specify the field_key individually in the template. Probably need a better
            #  approach to tackle this.
            data_source = f"./data/time_series/batch/node_{row.node_idx}.csv"
            data_sources.update({row.node_idx: data_source})
            # Process volumes: Wrap strings with 'work' in QuotedString
            raw_vols = [
                '/sys:/rootfs/sys:ro',
                '/proc:/rootfs/proc:ro',
                '/etc:/rootfs/etc:ro',
                f"./node{row.node_idx}/config.yaml:/work/settings/config.yaml",  # this file name is static
                f"./node{row.node_idx}/lookup.csv:/work/settings/lookup.csv",
                f"./node{row.node_idx}/influxdb.json:/work/secret/influxdb.json",  # this file name is static
                f"./node{row.node_idx}/node{row.node_idx}.cid:/work/settings/node{row.node_idx}.cid",
            ]
            if os.path.exists(data_source):
                data_file = os.path.basename(data_source)
                raw_vols.append(f"./node{row.node_idx}/{data_file}:/work/data/time_series/{data_file}")
            final_vols = [QuotedString(v) if 'work' in v else v for v in raw_vols]

            services_config[row.service_name] = {
                'image': f"{name_image}:1.0",
                'container_name': row.service_name,
                'restart': QuotedString('no'),
                'volumes': final_vols,
                'environment': {
                    'HOST_PROC': '/rootfs/proc',
                    'HOST_SYS': '/rootfs/sys',
                    'HOST_ETC': '/rootfs/etc'
                },
                'ports': [QuotedString(f"{start_port + row.node_idx}:61850")],
                'networks': [f"{group_network}-proxy"]
            }

        group_yaml = DockerComposeBuilder()
        group_yaml.add_network(group_network)
        group_yaml.bulk_add_services(services_config)
        group_yaml.export_compose_file(f"{current_group_dir}/docker-compose.yml")

        frame.apply(lambda r: update_node_configs(r, dict_config, path_scl, path_secret, data_sources, df_lookup),
                    axis=1)


if __name__ == "__main__":
    """
    Double-check and modify the settings below before running the batch builder.
    """

    SETTINGS = {
        'name_image': 'mega_sim_testing',
        'group_network': 'influxdb_network',
        'max_apps': 10,
        'start_port': 43301,
        'dir_output': './container/batch/mini_pv_batch/output'
    }

    PROJECT_DIR = './container/batch/mini_pv_batch'
    build_yaml_batch(
        path_mapping=f"{PROJECT_DIR}/data_mapping.csv",
        path_config=f"{PROJECT_DIR}/config.yaml",
        path_lookup=f"{PROJECT_DIR}/IEC61850_DA_lookup_mini_mega.csv",
        path_scl=f"{PROJECT_DIR}/IEC61850_DER_v1_mini.cid",  # all containers use the same data model
        path_secret=f"{PROJECT_DIR}/influxdb.json",
        **SETTINGS
    )