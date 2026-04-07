// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://ppklau.github.io',
	base: '/network_automation_lab',
	integrations: [
		starlight({
			title: 'ACME Investments — Network Automation Lab',
			description: 'A practitioner lab guide for network automation at a financial services firm. Spine-leaf fabric, multi-region BGP, GitLab CI/CD, Batfish compliance verification, and MiFID II traceability — on a 16GB laptop.',
			logo: {
				light: './src/assets/logo-light.svg',
				dark: './src/assets/logo-dark.svg',
				replacesTitle: false,
			},
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/ppklau' },
			],
			editLink: {
				baseUrl: 'https://github.com/ppklau/network_automation_lab/edit/main/site/',
			},
			customCss: ['./src/styles/custom.css'],
			sidebar: [
				{
					label: 'Architecture',
					items: [
						{ label: 'Global Overview', slug: 'architecture' },
						{ label: 'EMEA — London', slug: 'architecture/emea' },
						{ label: 'Americas — New York', slug: 'architecture/americas' },
						{ label: 'APAC — Singapore', slug: 'architecture/apac' },
						{ label: 'EU Regulatory — Frankfurt', slug: 'architecture/frankfurt' },
					],
				},
				{ label: 'Preface', slug: 'preface' },
				{
					label: 'Part 1 — Setting the Scene',
					items: [
						{ label: 'ACME Investments', slug: 'part1/01-acme-introduction' },
						{ label: 'Lab Setup', slug: 'part1/02-lab-setup' },
						{ label: 'Exploring the Environment', slug: 'part1/03-exploring-the-environment' },
					],
				},
				{
					label: 'Part 2 — Source of Truth',
					items: [
						{ label: 'Why a Source of Truth?', slug: 'part2/04-why-sot' },
						{ label: 'SoT Structure', slug: 'part2/05-sot-structure' },
						{ label: 'The Intent Layer', slug: 'part2/06-intent-layer' },
						{ label: 'Schema Validation', slug: 'part2/07-schema-validation' },
					],
				},
				{
					label: 'Part 3 — Config Generation',
					items: [
						{ label: 'Config Generation', slug: 'part3/08-config-generation' },
						{ label: 'Your First Push', slug: 'part3/09-your-first-push' },
					],
				},
				{
					label: 'Part 4 — The Pipeline',
					items: [
						{ label: 'The Pipeline', slug: 'part4/10-the-pipeline' },
						{ label: 'Change Freeze', slug: 'part4/11-change-freeze' },
					],
				},
				{
					label: 'Part 5 — Intent Verification',
					items: [
						{ label: 'Intent Verification', slug: 'part5/12-intent-verification' },
						{ label: 'Compliance as Code', slug: 'part5/13-compliance-as-code' },
					],
				},
				{
					label: 'Part 6 — Day-2 Operations',
					items: [
						{ label: 'Day-2 Overview', slug: 'part6/14-day2-overview' },
						{ label: 'Health and Drift', slug: 'part6/15-health-and-drift' },
						{ label: 'Compliance Reporting', slug: 'part6/16-compliance-reporting' },
						{ label: 'BGP Monitoring', slug: 'part6/17-bgp-monitoring' },
						{ label: 'Maintenance Operations', slug: 'part6/18-maintenance-operations' },
						{ label: 'Decommission and Hygiene', slug: 'part6/19-decommission-and-hygiene' },
					],
				},
				{
					label: 'Part 7 — Hardware Lifecycle & Monitoring',
					items: [
						{ label: 'Hardware Lifecycle', slug: 'part7/20-hardware-lifecycle-intro' },
						{ label: 'Leaf RMA', slug: 'part7/21-leaf-rma' },
						{ label: 'Border RMA', slug: 'part7/22-border-rma' },
						{ label: 'ZTP Branch Provisioning', slug: 'part7/23-ztp-branch' },
						{ label: 'OS Upgrade', slug: 'part7/24-os-upgrade' },
						{ label: 'Monitoring Introduction', slug: 'part7/25-monitoring-intro' },
						{ label: 'Dashboards', slug: 'part7/26-dashboards' },
						{ label: 'Alerting', slug: 'part7/27-alerting' },
					],
				},
				{
					label: 'Part 9 — Advanced Topics',
					items: [
						{ label: 'Advanced Topics', slug: 'part9/28-advanced-intro' },
						{ label: 'Auto-Remediation', slug: 'part9/29-auto-remediation' },
						{ label: 'Staged Rollout', slug: 'part9/30-staged-rollout' },
						{ label: 'Bulk Import', slug: 'part9/31-bulk-import' },
						{ label: 'Capstone', slug: 'part9/32-capstone' },
					],
				},
				{
					label: 'Appendix',
					items: [
						{ label: 'Glossary', slug: 'appendix/a-glossary' },
						{ label: 'Quick Reference', slug: 'appendix/b-quick-reference' },
					],
				},
			],
		}),
	],
});
