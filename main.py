import boto3
import time
import json
import base64
from botocore.exceptions import ClientError

# ============================================================
# AWS CONFIGURATION
# ============================================================

REGION = "ap-south-1"

VPC_CIDR = "10.0.0.0/16"
SUBNET1_CIDR = "10.0.1.0/24"
SUBNET2_CIDR = "10.0.2.0/24"

VPC_NAME = "Task8-VPC"
ALB_NAME = "task8-alb"
TARGET_GROUP_NAME = "task8-target-group"
ASG_NAME = "task8-asg"
LAUNCH_TEMPLATE_NAME = "task8-launch-template"

INSTANCE_TYPE = "t3.micro"

EC2_ROLE_NAME = "Task8-EC2-SSM-Role"
INSTANCE_PROFILE_NAME = "Task8-EC2-SSM-Profile"


# ============================================================
# AWS CLIENTS
# ============================================================

ec2 = boto3.client("ec2", region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)
autoscaling = boto3.client("autoscaling", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
iam = boto3.client("iam")


# ============================================================
# GET UBUNTU AMI
# ============================================================

def get_ubuntu_ami():

    print("Getting latest Ubuntu AMI...")

    parameter_name = (
        "/aws/service/canonical/ubuntu/server/24.04/"
        "stable/current/amd64/hvm/ebs-gp3/ami-id"
    )

    response = ssm.get_parameter(
        Name=parameter_name
    )

    ami_id = response["Parameter"]["Value"]

    print("Ubuntu AMI:", ami_id)

    return ami_id


# ============================================================
# CREATE EC2 IAM ROLE FOR SSM
# ============================================================

def create_ec2_role():

    print("Checking EC2 IAM Role...")

    try:

        iam.get_role(
            RoleName=EC2_ROLE_NAME
        )

        print("EC2 IAM Role already exists.")

    except iam.exceptions.NoSuchEntityException:

        print("Creating EC2 IAM Role...")

        trust_policy = {
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

        iam.create_role(
            RoleName=EC2_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(
                trust_policy
            )
        )

        iam.attach_role_policy(
            RoleName=EC2_ROLE_NAME,
            PolicyArn=(
                "arn:aws:iam::aws:policy/"
                "AmazonSSMManagedInstanceCore"
            )
        )

        print("EC2 IAM Role created.")

        time.sleep(10)


# ============================================================
# CREATE INSTANCE PROFILE
# ============================================================

def create_instance_profile():

    print("Checking Instance Profile...")

    try:

        iam.get_instance_profile(
            InstanceProfileName=INSTANCE_PROFILE_NAME
        )

        print("Instance Profile already exists.")

    except iam.exceptions.NoSuchEntityException:

        print("Creating Instance Profile...")

        iam.create_instance_profile(
            InstanceProfileName=INSTANCE_PROFILE_NAME
        )

        time.sleep(5)

        iam.add_role_to_instance_profile(
            InstanceProfileName=INSTANCE_PROFILE_NAME,
            RoleName=EC2_ROLE_NAME
        )

        print("Instance Profile created.")

        time.sleep(10)


# ============================================================
# CREATE VPC
# ============================================================

def create_vpc():

    print("\nCreating VPC...")

    response = ec2.create_vpc(
        CidrBlock=VPC_CIDR
    )

    vpc_id = response["Vpc"]["VpcId"]

    ec2.create_tags(
        Resources=[vpc_id],
        Tags=[
            {
                "Key": "Name",
                "Value": VPC_NAME
            }
        ]
    )

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

    print("VPC created:", vpc_id)

    return vpc_id


# ============================================================
# CREATE INTERNET GATEWAY
# ============================================================

def create_internet_gateway(vpc_id):

    print("\nCreating Internet Gateway...")

    response = ec2.create_internet_gateway()

    igw_id = response[
        "InternetGateway"
    ]["InternetGatewayId"]

    ec2.create_tags(
        Resources=[igw_id],
        Tags=[
            {
                "Key": "Name",
                "Value": "Task8-IGW"
            }
        ]
    )

    ec2.attach_internet_gateway(
        InternetGatewayId=igw_id,
        VpcId=vpc_id
    )

    print("Internet Gateway:", igw_id)

    return igw_id


# ============================================================
# CREATE SUBNETS
# ============================================================

def create_subnets(vpc_id):

    print("\nCreating Subnet 1...")

    subnet1_response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=SUBNET1_CIDR,
        AvailabilityZone=f"{REGION}a"
    )

    subnet1_id = subnet1_response[
        "Subnet"
    ]["SubnetId"]

    ec2.create_tags(
        Resources=[subnet1_id],
        Tags=[
            {
                "Key": "Name",
                "Value": "Task8-Public-Subnet-1"
            }
        ]
    )

    print("Subnet 1:", subnet1_id)

    print("\nCreating Subnet 2...")

    subnet2_response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=SUBNET2_CIDR,
        AvailabilityZone=f"{REGION}b"
    )

    subnet2_id = subnet2_response[
        "Subnet"
    ]["SubnetId"]

    ec2.create_tags(
        Resources=[subnet2_id],
        Tags=[
            {
                "Key": "Name",
                "Value": "Task8-Public-Subnet-2"
            }
        ]
    )

    print("Subnet 2:", subnet2_id)

    return subnet1_id, subnet2_id


# ============================================================
# CREATE ROUTE TABLE
# ============================================================

def create_route_table(vpc_id, igw_id, subnet1_id, subnet2_id):

    print("\nCreating Route Table...")

    response = ec2.create_route_table(
        VpcId=vpc_id
    )

    route_table_id = response[
        "RouteTable"
    ]["RouteTableId"]

    ec2.create_tags(
        Resources=[route_table_id],
        Tags=[
            {
                "Key": "Name",
                "Value": "Task8-Public-Route-Table"
            }
        ]
    )

    ec2.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=igw_id
    )

    ec2.associate_route_table(
        RouteTableId=route_table_id,
        SubnetId=subnet1_id
    )

    ec2.associate_route_table(
        RouteTableId=route_table_id,
        SubnetId=subnet2_id
    )

    print("Route Table:", route_table_id)


# ============================================================
# CREATE SECURITY GROUPS
# ============================================================

def create_security_groups(vpc_id):

    print("\nCreating ALB Security Group...")

    alb_sg_response = ec2.create_security_group(
        GroupName="Task8-ALB-SG",
        Description="Security Group for Task8 ALB",
        VpcId=vpc_id
    )

    alb_sg_id = alb_sg_response["GroupId"]

    ec2.authorize_security_group_ingress(
        GroupId=alb_sg_id,
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

    print("ALB Security Group:", alb_sg_id)

    print("\nCreating EC2 Security Group...")

    ec2_sg_response = ec2.create_security_group(
        GroupName="Task8-EC2-SG",
        Description="Security Group for Task8 EC2",
        VpcId=vpc_id
    )

    ec2_sg_id = ec2_sg_response["GroupId"]

    ec2.authorize_security_group_ingress(
        GroupId=ec2_sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 5000,
                "ToPort": 5000,
                "UserIdGroupPairs": [
                    {
                        "GroupId": alb_sg_id
                    }
                ]
            }
        ]
    )

    print("EC2 Security Group:", ec2_sg_id)

    return alb_sg_id, ec2_sg_id


# ============================================================
# USER DATA
# ============================================================

def create_user_data():

    user_data = """#!/bin/bash

apt-get update -y

apt-get install -y python3 python3-pip python3-venv

mkdir -p /opt/task8

cd /opt/task8

python3 -m venv venv

/opt/task8/venv/bin/pip install flask

cat > /opt/task8/app.py <<'PYTHON'
from flask import Flask
import socket

app = Flask(__name__)

@app.route("/")
def home():

    hostname = socket.gethostname()

    return (
        "<html>"
        "<head>"
        "<title>AWS Task 8</title>"
        "</head>"
        "<body>"
        "<h1>AWS Task 8 Application</h1>"
        "<h2>Application is running successfully</h2>"
        "<p>Server: " + hostname + "</p>"
        "<p>Load Balancer + Auto Scaling</p>"
        "</body>"
        "</html>"
    )

app.run(
    host="0.0.0.0",
    port=5000
)
PYTHON

cat > /etc/systemd/system/task8.service <<'SERVICE'
[Unit]
Description=Task 8 Flask Application
After=network.target

[Service]
WorkingDirectory=/opt/task8
ExecStart=/opt/task8/venv/bin/python /opt/task8/app.py
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload

systemctl enable task8

systemctl start task8
"""

    return base64.b64encode(
        user_data.encode()
    ).decode()


# ============================================================
# CREATE LAUNCH TEMPLATE
# ============================================================

def create_launch_template(ami_id, ec2_sg_id):

    print("\nCreating Launch Template...")

    user_data = create_user_data()

    try:

        response = ec2.create_launch_template(
            LaunchTemplateName=LAUNCH_TEMPLATE_NAME,
            LaunchTemplateData={
                "ImageId": ami_id,

                "InstanceType": INSTANCE_TYPE,

                "IamInstanceProfile": {
                    "Name": INSTANCE_PROFILE_NAME
                },

                "SecurityGroupIds": [
                    ec2_sg_id
                ],

                "UserData": user_data
            }
        )

        launch_template_id = response[
            "LaunchTemplate"
        ]["LaunchTemplateId"]

        print(
            "Launch Template:",
            launch_template_id
        )

        return launch_template_id

    except ClientError as e:

        if "already exists" in str(e):

            response = ec2.describe_launch_templates(
                LaunchTemplateNames=[
                    LAUNCH_TEMPLATE_NAME
                ]
            )

            launch_template_id = response[
                "LaunchTemplates"
            ][0]["LaunchTemplateId"]

            print(
                "Launch Template already exists:",
                launch_template_id
            )

            return launch_template_id

        raise


# ============================================================
# CREATE TARGET GROUP
# ============================================================

def create_target_group(vpc_id):

    print("\nCreating Target Group...")

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

    target_group_arn = response[
        "TargetGroups"
    ][0]["TargetGroupArn"]

    print(
        "Target Group:",
        target_group_arn
    )

    return target_group_arn


# ============================================================
# CREATE ALB
# ============================================================

def create_alb(
    subnet1_id,
    subnet2_id,
    alb_sg_id
):

    print("\nCreating Application Load Balancer...")

    response = elbv2.create_load_balancer(

        Name=ALB_NAME,

        Subnets=[
            subnet1_id,
            subnet2_id
        ],

        SecurityGroups=[
            alb_sg_id
        ],

        Scheme="internet-facing",

        Type="application",

        IpAddressType="ipv4"
    )

    load_balancer = response[
        "LoadBalancers"
    ][0]

    alb_arn = load_balancer[
        "LoadBalancerArn"
    ]

    alb_dns = load_balancer[
        "DNSName"
    ]

    print("ALB ARN:", alb_arn)

    print("ALB DNS:", alb_dns)

    return alb_arn, alb_dns


# ============================================================
# CREATE ALB LISTENER
# ============================================================

def create_listener(
    alb_arn,
    target_group_arn
):

    print("\nCreating ALB Listener...")

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

    listener_arn = response[
        "Listeners"
    ][0]["ListenerArn"]

    print(
        "Listener:",
        listener_arn
    )


# ============================================================
# CREATE AUTO SCALING GROUP
# ============================================================

def create_auto_scaling_group(
    launch_template_id,
    subnet1_id,
    subnet2_id,
    target_group_arn
):

    print("\nCreating Auto Scaling Group...")

    try:

        autoscaling.create_auto_scaling_group(

            AutoScalingGroupName=ASG_NAME,

            LaunchTemplate={
                "LaunchTemplateId":
                    launch_template_id,

                "Version": "$Latest"
            },

            MinSize=1,

            MaxSize=4,

            DesiredCapacity=1,

            VPCZoneIdentifier=(
                subnet1_id + "," + subnet2_id
            ),

            TargetGroupARNs=[
                target_group_arn
            ],

            HealthCheckType="ELB",

            HealthCheckGracePeriod=180
        )

        print(
            "Auto Scaling Group created:",
            ASG_NAME
        )

    except ClientError as e:

        if "already exists" in str(e):

            print(
                "Auto Scaling Group already exists."
            )

        else:
            raise


# ============================================================
# CREATE CPU TARGET TRACKING POLICY
# ============================================================

def create_scaling_policy():

    print("\nCreating CPU Auto Scaling Policy...")

    autoscaling.put_scaling_policy(

        AutoScalingGroupName=ASG_NAME,

        PolicyName="Task8-CPU-TargetTracking",

        PolicyType="TargetTrackingScaling",

        TargetTrackingConfiguration={

            "PredefinedMetricSpecification": {

                "PredefinedMetricType":
                    "ASGAverageCPUUtilization"
            },

            "TargetValue": 50.0,

            "DisableScaleIn": False
        }
    )

    print(
        "CPU Target Tracking Policy created."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("============================================")
    print("       AWS TASK 8 AUTOMATION")
    print("============================================")

    # 1. AMI
    ami_id = get_ubuntu_ami()

    # 2. EC2 IAM Role
    create_ec2_role()

    # 3. Instance Profile
    create_instance_profile()

    # 4. VPC
    vpc_id = create_vpc()

    # 5. Internet Gateway
    igw_id = create_internet_gateway(
        vpc_id
    )

    # 6. Subnets
    subnet1_id, subnet2_id = create_subnets(
        vpc_id
    )

    # 7. Route Table
    create_route_table(
        vpc_id,
        igw_id,
        subnet1_id,
        subnet2_id
    )

    # 8. Security Groups
    alb_sg_id, ec2_sg_id = create_security_groups(
        vpc_id
    )

    # 9. Launch Template
    launch_template_id = create_launch_template(
        ami_id,
        ec2_sg_id
    )

    # 10. Target Group
    target_group_arn = create_target_group(
        vpc_id
    )

    # 11. Application Load Balancer
    alb_arn, alb_dns = create_alb(
        subnet1_id,
        subnet2_id,
        alb_sg_id
    )

    # Wait for ALB to become active
    print("\nWaiting for ALB...")

    time.sleep(20)

    # 12. Listener
    create_listener(
        alb_arn,
        target_group_arn
    )

    # 13. Auto Scaling Group
    create_auto_scaling_group(
        launch_template_id,
        subnet1_id,
        subnet2_id,
        target_group_arn
    )

    # 14. Scaling Policy
    create_scaling_policy()

    print("\n")
    print("============================================")
    print("       TASK 8 DEPLOYMENT COMPLETED")
    print("============================================")

    print("\nVPC:")
    print(vpc_id)

    print("\nSubnet 1:")
    print(subnet1_id)

    print("\nSubnet 2:")
    print(subnet2_id)

    print("\nALB DNS:")
    print(alb_dns)

    print("\nApplication URL:")
    print("http://" + alb_dns)

    print("\nAuto Scaling Group:")
    print(ASG_NAME)

    print("\nMinimum Instances: 1")
    print("Maximum Instances: 4")
    print("Desired Instances: 1")
    print("CPU Target: 50%")

    print("\n============================================")


if __name__ == "__main__":
    main()