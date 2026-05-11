# AWS deployment (real MuseTalk, EC2 GPU)

This is the recipe for hosting the **real-mode** backend on a single EC2
instance with a GPU, which the Webex Desk reaches over HTTPS. The frontend
can either be served from the same box (simplest) or hosted separately.

The whole thing — quota check → EC2 launched → first real MuseTalk MP4 —
is about **30–45 minutes the first time** and **~2 minutes** for every
demo session after that (just `aws ec2 start-instances`, then later
`stop-instances`).

> Compute cost for a 30-minute demo: **~$0.30** on-demand, **~$0.10** spot.

---

## 0. Prerequisites on AWS

1. **An AWS account you have permission to launch EC2 instances in.**
2. **GPU service quota.** New AWS accounts have a quota of `0` for "Running
   On-Demand G and VT instances". Request an increase to **at least `4`**
   (`g4dn.xlarge` is 4 vCPU = 4 quota units):

   ```text
   AWS Console → Service Quotas → AWS services → Amazon EC2
                → "Running On-Demand G and VT instances"
                → Request quota increase → 4
   ```

   This usually takes 0–24 hours. Skip if you already have the quota.

3. **A keypair in the target region.** EC2 → Network & Security → Key Pairs
   → Create. Save the `.pem` file; you'll SSH with it.

4. **AWS CLI configured locally** so we can drive the instance from your
   laptop:

   ```powershell
   aws --version    # v2 recommended
   aws configure    # set access key / secret / region
   ```

---

## 1. Launch the EC2 instance

We use the **Deep Learning Base GPU AMI (Ubuntu 22.04)** so NVIDIA drivers,
CUDA 11.8, and cuDNN are already installed and tested. (Saves ~30 minutes
of NVIDIA driver pain that *will* go wrong otherwise.)

### Find the latest AMI ID for your region

```powershell
aws ec2 describe-images `
  --owners amazon `
  --region us-east-1 `
  --filters "Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*" `
  --query "reverse(sort_by(Images, &CreationDate))[:1].{ID:ImageId,Name:Name,Date:CreationDate}" `
  --output table
```

Copy the `ID` column (something like `ami-0abc...`).

### Launch the instance

```powershell
$AMI       = "ami-XXXXXXXX"            # paste the AMI ID from above
$KEY_NAME  = "your-keypair-name"
$REGION    = "us-east-1"
$NAME      = "avatar-demo"

# Create a security group that allows SSH from your IP and HTTPS from anywhere.
$MY_IP   = (Invoke-WebRequest -UseBasicParsing https://checkip.amazonaws.com).Content.Trim() + "/32"
$VPC_ID  = aws ec2 describe-vpcs --region $REGION --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text

$SG_ID = aws ec2 create-security-group `
  --region $REGION `
  --group-name avatar-demo-sg `
  --description "AI avatar demo (SSH from me, HTTPS from internet)" `
  --vpc-id $VPC_ID `
  --query "GroupId" --output text

aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID `
  --protocol tcp --port 22  --cidr $MY_IP
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID `
  --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID `
  --protocol tcp --port 80  --cidr 0.0.0.0/0   # only used by Caddy for cert challenge

# Launch with a 200 GB gp3 root volume (DL AMI is ~150 GB; plus weights + outputs).
$INSTANCE_ID = aws ec2 run-instances `
  --region $REGION `
  --image-id $AMI `
  --instance-type g4dn.xlarge `
  --key-name $KEY_NAME `
  --security-group-ids $SG_ID `
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=200,VolumeType=gp3}' `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" `
  --query "Instances[0].InstanceId" --output text

aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID

$PUB_IP = aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID `
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text

Write-Host "Instance: $INSTANCE_ID"
Write-Host "Public IP: $PUB_IP"
Write-Host "SSH: ssh -i $KEY_NAME.pem ubuntu@$PUB_IP"
```

> If your AWS organization blocks public IPs, you'll need to attach an
> Elastic IP from a NAT'd subnet or run the instance in a private subnet
> reachable via your corporate VPN. Tell IT what you need; the rest of
> the recipe is identical.

### Spot variant (optional, ~70% cheaper)

Replace the `run-instances` call with:

```powershell
aws ec2 run-instances ... --instance-market-options 'MarketType=spot,SpotOptions={InstanceInterruptionBehavior=stop,SpotInstanceType=persistent}'
```

You'll lose the box if AWS reclaims capacity, but `start-instances` will
restart it in place since the EBS volume persists.

---

## 2. SSH in and bootstrap

```bash
ssh -i your-keypair-name.pem ubuntu@<PUBLIC_IP>

# Verify the GPU + driver — must say something like "Tesla T4"
nvidia-smi

# Pull the bootstrap script (or scp it from your laptop)
curl -fsSL https://raw.githubusercontent.com/<your-fork>/ai-avatar-desk-demo/main/scripts/aws_bootstrap.sh \
  -o aws_bootstrap.sh

# Or if you have not pushed the repo yet:
#   scp -i your-keypair-name.pem -r path/to/ai-avatar-desk-demo ubuntu@<IP>:~
#   then run scripts/aws_bootstrap.sh from inside the copied tree

bash aws_bootstrap.sh
```

The bootstrap script (also copied below) does:

1. Installs system `ffmpeg` and Python 3.10 (used by the MuseTalk venv).
2. Sets up our backend's Python 3.10 venv (Kokoro, FastAPI, etc.).
3. Clones MuseTalk into `third_party/MuseTalk` and creates *its own*
   Python 3.10 venv with CUDA-enabled torch + `mmcv`/`mmdet`/`mmpose`.
4. Downloads MuseTalk weights (~2 GB).
5. Drops a placeholder avatar so the pipeline has something to run on.
6. Installs Caddy and writes a `Caddyfile` that:
   - Terminates HTTPS via Let's Encrypt
   - Serves the built React frontend
   - Proxies `/api/*` and `/outputs/*` to the FastAPI backend
   - Requires a bearer token on `POST /api/jobs` so randos can't burn
     your GPU time.

When it finishes you'll see:

```text
==== ai-avatar-desk-demo bootstrap complete ====
Public URL: https://<EC2 hostname>
API token : <random 32-byte token>
Run:
  sudo systemctl start avatar-backend
  sudo systemctl enable avatar-backend
```

---

## 3. Verify real-mode generation

```bash
# On the EC2 box
sudo systemctl start avatar-backend
sudo systemctl status avatar-backend --no-pager | head -20

curl https://<EC2 host>/api/health
# -> {"status":"ok"}

curl -X POST https://<EC2 host>/api/jobs \
  -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, this is a real MuseTalk render."}'
# -> {"job_id":"...","status":"queued","mode":"real"}

# Poll until completed (real-mode render on T4 takes ~3-5x audio length)
JOB=...
curl https://<EC2 host>/api/jobs/$JOB
```

Then open `https://<EC2 host>/` in your laptop browser to confirm the SPA
loads and the video plays. That same URL goes into the Webex Desk Web App.

---

## 4. Webex Desk configuration

In Cisco Control Hub (or via xConfiguration over xAPI):

```text
WebEngine: Enabled
UserInterface CustomMessage: "AI Avatar Demo"
WebApp: https://<EC2 host>/
```

The Desk just opens that URL like any browser. No special setup beyond
making sure the Desk can resolve and reach the host.

If your Desk is locked down to only allow corporate hosts, you'll need
either:
- a CNAME from your corporate domain to the EC2 hostname, plus a corp
  certificate (most enterprises do this via ACM + a public ALB rather
  than EC2-direct);
- or a private deployment (VPN / Direct Connect) — see the alt section
  in `docs/WEBEX_DESK_DEPLOYMENT.md`.

---

## 5. Day-to-day cost control

```powershell
# Stop the instance when you're done demoing — EBS persists, you only pay $16/mo for storage.
aws ec2 stop-instances --region us-east-1 --instance-ids $INSTANCE_ID

# Restart in ~30 seconds when you need to demo again
aws ec2 start-instances --region us-east-1 --instance-ids $INSTANCE_ID
aws ec2 wait instance-running --region us-east-1 --instance-ids $INSTANCE_ID

# The public IP changes on each start unless you allocate an Elastic IP:
aws ec2 allocate-address --region us-east-1 --domain vpc
aws ec2 associate-address --region us-east-1 --instance-id $INSTANCE_ID --allocation-id eipalloc-...
```

Allocate an Elastic IP if you don't want the URL to change. EIPs are free
**while attached to a running instance**, **$0.005/hr** (~$3.60/mo) when
detached or attached to a stopped instance.

---

## 6. Troubleshooting (AWS-specific)

| Symptom | Likely cause | Fix |
|---|---|---|
| `VcpuLimitExceeded` on launch | GPU quota = 0 | Request quota bump (Section 0, step 2) |
| `nvidia-smi` not found on the instance | Wrong AMI (didn't pick the Deep Learning AMI) | Re-launch with the correct AMI ID |
| MuseTalk says `CUDA out of memory` | Another job leaked VRAM | `sudo systemctl restart avatar-backend` |
| Caddy fails to get a cert | Port 80 blocked or DNS not pointed at the EC2 IP | Confirm SG allows 80, and that your DNS A-record points at the public IP |
| Backend returns 401 from the SPA | Frontend not sending the bearer token | Set `VITE_BACKEND_TOKEN` at build time, or move auth to a header injected by Caddy |
| Webex Desk says "page can't be loaded" | Self-signed cert / cert from a CA the Desk doesn't trust | Use Let's Encrypt (default in our Caddyfile) or your corp CA |
| First job in real mode takes ages | First MuseTalk run does heavy preprocessing of the avatar; subsequent jobs reuse the `.pkl` cache | Expected — second job and onward are 3–5× faster |

---

## 7. Going to production

This recipe is intentionally a single EC2 box. For an internal pilot it's
fine. If you need a "real" production deployment we'd add:

- **ALB** in front (HTTPS termination + access logging + WAF)
- **CloudFront** for the static SPA (cheaper egress than EC2)
- **Auto-scaling group** of 0–N g4dn.xlarge with scheduled scaling so the
  GPU only runs during business hours
- **S3 bucket** for `assets/outputs/*.mp4` instead of the local disk, with
  signed URLs
- **CloudWatch alarms** on instance health + GPU memory
- **AWS CDK / Terraform** to make the whole thing reproducible

I have skeletons of these in CDK; ask if/when you want them.
