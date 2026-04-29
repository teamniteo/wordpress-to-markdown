---
title: "How we killed our new AI product"
slug: "how-we-killed-our-new-ai-product"
date: "2026-04-09"
author: "Dejan Murko"
authorEmail: "dm@niteo.co"
authorBio: "Dejan is the co-founder of Niteo, a small SaaS studio that created Hakuto."
category: "Updates"
description: "How a failed attempt at building a Lovable competitor turned into an open-source site builder powered by Claude Code."
draft: false
---

I'm the co-founder of [Niteo](https://niteo.co), a small SaaS studio that's been around for almost 20 years. We've had our own custom framework for building websites for a long time. We loved working with Tailwind CSS and were happy with the results. The problem was always speed since getting a new page up and running required a designer and a developer, every time.

When I started using [Lovable](https://lovable.dev), I was blown away by how fast I could launch a site as a non-dev. But Lovable sites aren't great for SEO, and the platform is expanding into other directions, so it was never a solid long-term bet.

That got us thinking: why not build a Lovable for websites? We'd use Astro as the framework, let users bring their own API keys (because that's what we want), and host everything on Cloudflare for free.

So we built a prototype of the chat interface, used it for a while, hit a wall of bugs, invested more time, and eventually got it looking really nice:

![Hakuto app prototype](/images/blog/hakuto-app.png)

Unfortunately, it was still really buggy. Since we didn't have time to fix those bugs, I got frustrated and switched to Claude Code to keep editing the sites I was working on.

That's when the light bulb went off — why don't we just use Claude Code directly?

It took me a couple of days to figure out, but the Astro framework and the Skills we'd built were really the only things we needed. There is no paid product here.

Since we need it ourselves and had already promised it to a lot of people, we decided to open-source everything, build this website, and show you how to do it on your own.