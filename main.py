import boto3
import base64
import time
from botocore.exceptions import ClientError


# ============================================================
# CONFIGURATION
# ============================================================

REGION = "ap-south-1"

VPC_CIDR = "10.0.0.0/16"

SUBNET1_CIDR = "10.0.1.0/24"
SUBNET2_CIDR = "10.0.2.0/24"

AZ1 = "ap-south-1a"
AZ2 = "ap-south-1b"

VPC_NAME = "Task8-VPC"

ALB_NAME = "task8-alb"

TARGET_GROUP_NAME = "task8-target-group"

LAUNCH_TEMPLATE_NAME = "task8-launch-template"

ASG_NAME = "task8-asg"

ALB_SG_NAME = "Task8-ALB-SG"

EC2_SG_NAME = "Task8-EC2-SG"

INSTANCE_TYPE = "t3.micro"

MIN_SIZE = 1

DESIRED_SIZE = 1

MAX_SIZE = 4

CPU_TARGET = 50.0


# ============================================================
# AWS CLIENTS
# ============================================================

ec2 = boto3.client(
    "ec2",
    region_name=REGION
)

ssm = boto3.client(
    "ssm",
    region_name=REGION
)

iam = boto3.client(
    "iam",
    region_name=REGION
)

elbv2 = boto3.client(
    "elbv2",
    region_name=REGION
)

autoscaling = boto3.client(
    "autoscaling",
    region_name=REGION
)


# ============================================================
# UBUNTU AMI
# ============================================================

def get_ubuntu_ami():

    print("\nGetting latest Ubuntu AMI...")

    parameter = (
        "/aws/service/canonical/ubuntu/server/24.04/"
        "stable/current/amd64/hvm/ebs-gp3/ami-id"
    )

    response = ssm.get_parameter(
        Name=parameter
    )

    ami_id = response["Parameter"]["Value"]

    print("Ubuntu AMI:", ami_id)

    return ami_id


# ============================================================
# IAM ROLE
# ============================================================

def create_ec2_role():

    role_name = "Task8-EC2-SSM-Role"

    print("\nChecking EC2 IAM Role...")

    try:

        iam.get_role(
            RoleName=role_name
        )

        print("EC2 IAM Role already exists.")

    except iam.exceptions.NoSuchEntityException:

        print("Creating EC2 IAM Role...")

        trust_policy = """
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        """

        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy
        )

        print("EC2 IAM Role created.")

    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn=(
            "arn:aws:iam::aws:policy/"
            "AmazonSSMManagedInstanceCore"
        )
    )

    return role_name


# ============================================================
# INSTANCE PROFILE
# ============================================================

def create_instance_profile(role_name):

    profile_name = "Task8-EC2-SSM-Profile"

    print("\nChecking Instance Profile...")

    try:

        iam.get_instance_profile(
            InstanceProfileName=profile_name
        )

        print("Instance Profile already exists.")

    except iam.exceptions.NoSuchEntityException:

        print("Creating Instance Profile...")

        iam.create_instance_profile(
            InstanceProfileName=profile_name
        )

        time.sleep(3)

        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name,
            RoleName=role_name
        )

        print("Instance Profile created.")

    return profile_name


# ============================================================
# VPC
# ============================================================

def create_vpc():

    print("\nChecking VPC...")

    response = ec2.describe_vpcs(
        Filters=[
            {
                "Name": "cidr-block",
                "Values": [VPC_CIDR]
            },
            {
                "Name": "state",
                "Values": ["available"]
            }
        ]
    )

    if response["Vpcs"]:

        vpc_id = response["Vpcs"][0]["VpcId"]

        print(
            "Existing VPC reused:",
            vpc_id
        )

        return vpc_id

    print("Creating VPC...")

    response = ec2.create_vpc(
        CidrBlock=VPC_CIDR
    )

    vpc_id = response[
        "Vpc"
    ]["VpcId"]

    print(
        "VPC created:",
        vpc_id
    )

    # DNS support
    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsSupport={
            "Value": True
        }
    )

    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsHostnames={
            "Value": True
        }
    )

    return vpc_id


# ============================================================
# INTERNET GATEWAY
# ============================================================

def create_internet_gateway(vpc_id):

    print("\nChecking Internet Gateway...")

    response = ec2.describe_internet_gateways()

    for igw in response["InternetGateways"]:

        for attachment in igw.get(
            "Attachments",
            []
        ):

            if (
                attachment.get("VpcId")
                == vpc_id
            ):

                igw_id = igw[
                    "InternetGatewayId"
                ]

                print(
                    "Existing Internet Gateway reused:",
                    igw_id
                )

                return igw_id

    print("Creating Internet Gateway...")

    try:

        response = ec2.create_internet_gateway()

    except ClientError as e:

        if (
            e.response["Error"]["Code"]
            == "InternetGatewayLimitExceeded"
        ):

            raise Exception(
                "AWS Internet Gateway limit reached. "
                "Delete one unused Internet Gateway "
                "from AWS Console and run again."
            )

        raise

    igw_id = response[
        "InternetGateway"
    ]["InternetGatewayId"]

    ec2.attach_internet_gateway(
        InternetGatewayId=igw_id,
        VpcId=vpc_id
    )

    print(
        "Internet Gateway created:",
        igw_id
    )

    return igw_id


# ============================================================
# SUBNET
# ============================================================

def create_subnet(
    vpc_id,
    cidr,
    availability_zone
):

    print(
        "\nChecking subnet:",
        cidr
    )

    response = ec2.describe_subnets(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id]
            },
            {
                "Name": "cidr-block",
                "Values": [cidr]
            }
        ]
    )

    if response["Subnets"]:

        subnet_id = response[
            "Subnets"
        ][0]["SubnetId"]

        print(
            "Existing subnet reused:",
            subnet_id
        )

        return subnet_id

    print("Creating subnet...")

    response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=cidr,
        AvailabilityZone=availability_zone
    )

    subnet_id = response[
        "Subnet"
    ]["SubnetId"]

    ec2.modify_subnet_attribute(
        SubnetId=subnet_id,
        MapPublicIpOnLaunch={
            "Value": True
        }
    )

    print(
        "Subnet created:",
        subnet_id
    )

    return subnet_id


# ============================================================
# ROUTE TABLE
# ============================================================

def create_route_table(
    vpc_id,
    igw_id,
    subnet1_id,
    subnet2_id
):

    print("\nChecking Route Table...")

    response = ec2.describe_route_tables(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id]
            }
        ]
    )

    route_table_id = None

    for rt in response["RouteTables"]:

        for route in rt.get(
            "Routes",
            []
        ):

            if (
                route.get("GatewayId")
                == igw_id
                and
                route.get(
                    "DestinationCidrBlock"
                )
                == "0.0.0.0/0"
            ):

                route_table_id = rt[
                    "RouteTableId"
                ]

                break

        if route_table_id:
            break

    if route_table_id:

        print(
            "Existing Route Table reused:",
            route_table_id
        )

    else:

        print("Creating Route Table...")

        response = ec2.create_route_table(
            VpcId=vpc_id
        )

        route_table_id = response[
            "RouteTable"
        ]["RouteTableId"]

        try:

            ec2.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock="0.0.0.0/0",
                GatewayId=igw_id
            )

        except ClientError as e:

            if (
                "RouteAlreadyExists"
                not in str(e)
            ):
                raise

        print(
            "Route Table created:",
            route_table_id
        )

    # Associate subnet 1
    try:

        ec2.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet1_id
        )

    except ClientError as e:

        if (
            "Resource.AlreadyAssociated"
            not in str(e)
        ):
            pass

    # Associate subnet 2
    try:

        ec2.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet2_id
        )

    except ClientError as e:

        if (
            "Resource.AlreadyAssociated"
            not in str(e)
        ):
            pass

    return route_table_id


# ============================================================
# SECURITY GROUP
# ============================================================

def get_security_group(
    vpc_id,
    group_name,
    description
):

    print(
        "\nChecking Security Group:",
        group_name
    )

    response = ec2.describe_security_groups(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id]
            },
            {
                "Name": "group-name",
                "Values": [group_name]
            }
        ]
    )

    if response["SecurityGroups"]:

        sg_id = response[
            "SecurityGroups"
        ][0]["GroupId"]

        print(
            "Existing Security Group reused:",
            sg_id
        )

        return sg_id

    print("Creating Security Group...")

    response = ec2.create_security_group(
        GroupName=group_name,
        Description=description,
        VpcId=vpc_id
    )

    sg_id = response["GroupId"]

    print(
        "Security Group created:",
        sg_id
    )

    return sg_id


# ============================================================
# SECURITY RULES
# ============================================================

def configure_security_groups(
    alb_sg,
    ec2_sg
):

    print("\nConfiguring Security Group rules...")

    # ALB port 80
    try:

        ec2.authorize_security_group_ingress(
            GroupId=alb_sg,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ]
                }
            ]
        )

    except ClientError:

        pass

    # EC2 port 5000 from ALB only
    try:

        ec2.authorize_security_group_ingress(
            GroupId=ec2_sg,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5000,
                    "ToPort": 5000,
                    "UserIdGroupPairs": [
                        {
                            "GroupId": alb_sg
                        }
                    ]
                }
            ]
        )

    except ClientError:

        pass

    print(
        "Security Group rules configured."
    )


# ============================================================
# LAUNCH TEMPLATE
# ============================================================

def create_launch_template(
    ami_id,
    ec2_sg,
    profile_name
):

    print("\nChecking Launch Template...")

    user_data = """#!/bin/bash

set -e

apt-get update -y

apt-get install -y python3 python3-pip python3-venv curl snapd

systemctl enable --now snapd.socket || true

sleep 5

if ! snap list amazon-ssm-agent >/dev/null 2>&1
then
    snap install amazon-ssm-agent --classic
fi

systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service

systemctl restart snap.amazon-ssm-agent.amazon-ssm-agent.service

mkdir -p /opt/task8

python3 -m venv /opt/task8/venv

/opt/task8/venv/bin/pip install flask

cat > /opt/task8/app.py <<'PYEOF'

from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Application is running successfully"

app.run(
    host="0.0.0.0",
    port=5000
)

PYEOF


cat > /etc/systemd/system/task8.service <<'EOF'

[Unit]

Description=Task 8 Flask Application

After=network.target


[Service]

User=root

WorkingDirectory=/opt/task8

ExecStart=/opt/task8/venv/bin/python /opt/task8/app.py

Restart=always

RestartSec=5


[Install]

WantedBy=multi-user.target

EOF


systemctl daemon-reload

systemctl enable task8

systemctl restart task8

sleep 10

curl http://127.0.0.1:5000/

"""

    encoded_user_data = base64.b64encode(
        user_data.encode()
    ).decode()

    try:

        response = ec2.describe_launch_templates(
            LaunchTemplateNames=[
                LAUNCH_TEMPLATE_NAME
            ]
        )

        launch_template_id = response[
            "LaunchTemplates"
        ][0]["LaunchTemplateId"]

        print(
            "Existing Launch Template reused:",
            launch_template_id
        )

        # New version
        ec2.create_launch_template_version(

            LaunchTemplateId=
                launch_template_id,

            VersionDescription=
                "Task8 latest version",

            LaunchTemplateData={

                "ImageId": ami_id,

                "InstanceType":
                    INSTANCE_TYPE,

                "SecurityGroupIds": [
                    ec2_sg
                ],

                "IamInstanceProfile": {
                    "Name": profile_name
                },

                "UserData":
                    encoded_user_data
            }
        )

        print(
            "New Launch Template version created."
        )

        return launch_template_id

    except ClientError as e:

        if (
            "NotFoundException"
            not in str(e)
        ):
            raise

    print(
        "Creating Launch Template..."
    )

    response = ec2.create_launch_template(

        LaunchTemplateName=
            LAUNCH_TEMPLATE_NAME,

        LaunchTemplateData={

            "ImageId": ami_id,

            "InstanceType":
                INSTANCE_TYPE,

            "SecurityGroupIds": [
                ec2_sg
            ],

            "IamInstanceProfile": {
                "Name": profile_name
            },

            "UserData":
                encoded_user_data
        }
    )

    launch_template_id = response[
        "LaunchTemplate"
    ]["LaunchTemplateId"]

    print(
        "Launch Template created:",
        launch_template_id
    )

    return launch_template_id


# ============================================================
# TARGET GROUP
# ============================================================

def create_target_group(vpc_id):

    print("\nChecking Target Group...")

    try:

        response = elbv2.describe_target_groups(
            Names=[
                TARGET_GROUP_NAME
            ]
        )

        arn = response[
            "TargetGroups"
        ][0]["TargetGroupArn"]

        print(
            "Existing Target Group reused."
        )

        return arn

    except ClientError:

        pass

    print(
        "Creating Target Group..."
    )

    response = elbv2.create_target_group(

        Name=TARGET_GROUP_NAME,

        Protocol="HTTP",

        Port=5000,

        VpcId=vpc_id,

        TargetType="instance",

        HealthCheckProtocol="HTTP",

        HealthCheckPort="5000",

        HealthCheckPath="/",

        HealthCheckIntervalSeconds=30,

        HealthCheckTimeoutSeconds=5,

        HealthyThresholdCount=2,

        UnhealthyThresholdCount=3
    )

    arn = response[
        "TargetGroups"
    ][0]["TargetGroupArn"]

    print(
        "Target Group created."
    )

    return arn


# ============================================================
# ALB
# ============================================================

def create_alb(
    subnet1,
    subnet2,
    alb_sg
):

    print(
        "\nChecking Application Load Balancer..."
    )

    try:

        response = elbv2.describe_load_balancers(
            Names=[
                ALB_NAME
            ]
        )

        alb = response[
            "LoadBalancers"
        ][0]

        print(
            "Existing ALB reused."
        )

        return (
            alb["LoadBalancerArn"],
            alb["DNSName"]
        )

    except ClientError:

        pass

    print(
        "Creating Application Load Balancer..."
    )

    response = elbv2.create_load_balancer(

        Name=ALB_NAME,

        Subnets=[
            subnet1,
            subnet2
        ],

        SecurityGroups=[
            alb_sg
        ],

        Scheme="internet-facing",

        Type="application"
    )

    alb = response[
        "LoadBalancers"
    ][0]

    alb_arn = alb[
        "LoadBalancerArn"
    ]

    dns = alb[
        "DNSName"
    ]

    print(
        "ALB created:",
        dns
    )

    return alb_arn, dns


# ============================================================
# LISTENER
# ============================================================

def create_listener(
    alb_arn,
    target_group_arn
):

    print(
        "\nChecking ALB Listener..."
    )

    response = elbv2.describe_listeners(
        LoadBalancerArn=alb_arn
    )

    for listener in response[
        "Listeners"
    ]:

        if listener["Port"] == 80:

            print(
                "Existing Listener reused."
            )

            elbv2.modify_listener(

                ListenerArn=
                    listener["ListenerArn"],

                DefaultActions=[
                    {
                        "Type": "forward",

                        "TargetGroupArn":
                            target_group_arn
                    }
                ]
            )

            return listener[
                "ListenerArn"
            ]

    print(
        "Creating Listener..."
    )

    response = elbv2.create_listener(

        LoadBalancerArn=alb_arn,

        Protocol="HTTP",

        Port=80,

        DefaultActions=[
            {
                "Type": "forward",

                "TargetGroupArn":
                    target_group_arn
            }
        ]
    )

    return response[
        "Listeners"
    ][0]["ListenerArn"]


# ============================================================
# AUTO SCALING GROUP
# ============================================================

def create_asg(
    launch_template_id,
    subnet1,
    subnet2,
    target_group_arn
):

    print(
        "\nChecking Auto Scaling Group..."
    )

    try:

        response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                ASG_NAME
            ]
        )

        if response[
            "AutoScalingGroups"
        ]:

            print(
                "Existing ASG found. Updating..."
            )

            autoscaling.update_auto_scaling_group(

                AutoScalingGroupName=
                    ASG_NAME,

                MinSize=MIN_SIZE,

                DesiredCapacity=
                    DESIRED_SIZE,

                MaxSize=MAX_SIZE,

                VPCZoneIdentifier=
                    subnet1 + "," + subnet2,

                HealthCheckType="ELB",

                HealthCheckGracePeriod=600,

                LaunchTemplate={

                    "LaunchTemplateId":
                        launch_template_id,

                    "Version": "$Latest"
                }
            )

            return

    except ClientError:

        pass

    print(
        "Creating Auto Scaling Group..."
    )

    autoscaling.create_auto_scaling_group(

        AutoScalingGroupName=
            ASG_NAME,

        MinSize=MIN_SIZE,

        DesiredCapacity=
            DESIRED_SIZE,

        MaxSize=MAX_SIZE,

        VPCZoneIdentifier=
            subnet1 + "," + subnet2,

        TargetGroupARNs=[
            target_group_arn
        ],

        HealthCheckType="ELB",

        HealthCheckGracePeriod=600,

        LaunchTemplate={

            "LaunchTemplateId":
                launch_template_id,

            "Version": "$Latest"
        }
    )

    print(
        "Auto Scaling Group created."
    )


# ============================================================
# SCALING POLICY
# ============================================================

def create_scaling_policy():

    print(
        "\nConfiguring Auto Scaling Policy..."
    )

    autoscaling.put_scaling_policy(

        AutoScalingGroupName=
            ASG_NAME,

        PolicyName=
            "Task8-CPU-Target-Tracking",

        PolicyType=
            "TargetTrackingScaling",

        TargetTrackingConfiguration={

            "PredefinedMetricSpecification": {

                "PredefinedMetricType":
                    "ASGAverageCPUUtilization"
            },

            "TargetValue":
                CPU_TARGET,

            "DisableScaleIn":
                False
        }
    )

    print(
        "CPU target:",
        CPU_TARGET,
        "%"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n============================================"
    )

    print(
        "       AWS TASK 8 AUTOMATION"
    )

    print(
        "============================================"
    )

    # 1
    ami_id = get_ubuntu_ami()

    # 2
    role_name = create_ec2_role()

    # 3
    profile_name = create_instance_profile(
        role_name
    )

    # 4
    vpc_id = create_vpc()

    # 5
    igw_id = create_internet_gateway(
        vpc_id
    )

    # 6
    subnet1 = create_subnet(
        vpc_id,
        SUBNET1_CIDR,
        AZ1
    )

    # 7
    subnet2 = create_subnet(
        vpc_id,
        SUBNET2_CIDR,
        AZ2
    )

    # 8
    create_route_table(
        vpc_id,
        igw_id,
        subnet1,
        subnet2
    )

    # 9
    alb_sg = get_security_group(

        vpc_id,

        ALB_SG_NAME,

        "Task8 ALB Security Group"
    )

    # 10
    ec2_sg = get_security_group(

        vpc_id,

        EC2_SG_NAME,

        "Task8 EC2 Security Group"
    )

    # 11
    configure_security_groups(
        alb_sg,
        ec2_sg
    )

    # 12
    launch_template_id = create_launch_template(

        ami_id,

        ec2_sg,

        profile_name
    )

    # 13
    target_group_arn = create_target_group(
        vpc_id
    )

    # 14
    alb_arn, alb_dns = create_alb(

        subnet1,

        subnet2,

        alb_sg
    )

    # 15
    create_listener(

        alb_arn,

        target_group_arn
    )

    # 16
    create_asg(

        launch_template_id,

        subnet1,

        subnet2,

        target_group_arn
    )

    # 17
    create_scaling_policy()


    print(
        "\n============================================"
    )

    print(
        "          TASK 8 COMPLETED"
    )

    print(
        "============================================"
    )

    print(
        "\nVPC:",
        vpc_id
    )

    print(
        "\nALB:",
        alb_dns
    )

    print(
        "\nApplication URL:"
    )

    print(
        "http://" + alb_dns
    )

    print(
        "\nASG:",
        ASG_NAME
    )

    print(
        "\nCPU Target:",
        str(CPU_TARGET) + "%"
    )

    print(
        "\n============================================"
    )


if __name__ == "__main__":

    main()