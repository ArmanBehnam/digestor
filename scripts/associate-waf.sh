#!/bin/bash
# Retry WAF association - run this if the initial association failed due to propagation delay
# Usage: bash scripts/associate-waf.sh

WAF_ARN="arn:aws:wafv2:us-east-1:800712212732:regional/webacl/digestor-dev-waf/134e2bc9-acbe-415b-a05f-352828d44472"
ALB_ARN="arn:aws:elasticloadbalancing:us-east-1:800712212732:loadbalancer/app/digestor-dev/1a0db011f0170ecd"

echo "Associating WAF with ALB..."
for i in 1 2 3 4 5; do
  MSYS_NO_PATHCONV=1 aws wafv2 associate-web-acl \
    --web-acl-arn "$WAF_ARN" \
    --resource-arn "$ALB_ARN" \
    --region us-east-1 2>&1

  if [ $? -eq 0 ]; then
    echo "WAF associated successfully!"
    exit 0
  fi

  echo "Attempt $i failed, waiting 60s before retry..."
  sleep 60
done

echo "WAF association failed after 5 attempts. Try again later or use AWS Console:"
echo "  WAFv2 > Web ACLs > digestor-dev-waf > Associated AWS resources > Add"
