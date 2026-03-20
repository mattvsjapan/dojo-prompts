---
name: content-discovery
description: |
  Find native Japanese content that matches the user's personal taste.
  Walks through a discovery workflow using web search in Japanese.
allowed-tools:
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# Content Discovery

Find native Japanese content that genuinely matches your taste — not a generic "good for learners" list.

## Usage

Run `/content-discovery` and the skill will walk you through the process interactively.

## Step 1 — Understand their taste and level

Walk the user through these questions **one at a time**. Ask one question, wait for their answer, then move to the next. Do not present all questions at once.

1. First, ask: What are 3–5 things you enjoy in English? (shows, podcasts, games, books, YouTube channels, hobbies, genres, topics — anything)
2. Then ask: Is there anything you actively dislike or find boring?
3. Then ask: Have you tried any Japanese content before? If so, what was it and how did you feel about it?
4. Finally, ask about their comprehension level: Roughly how much do you understand when you listen to native Japanese? (e.g., "I catch a few words," "I follow the gist but miss details," "I understand most of it but struggle with fast speech or specialized vocabulary"). If they're unsure, ask what they've watched recently and how much they felt they understood.

After gathering all answers, build a private mental profile of their actual taste *and* their comprehension level. The goal is to find content that is both **entertaining and comprehensible** — something they genuinely want to watch that they can also meaningfully follow.

## Step 2 — Think in Japanese

Before searching, switch your reasoning entirely into Japanese. Do not think about "what is good for language learners." Instead think:

> "If a native Japanese speaker with these exact tastes wanted something to watch/listen to/read, where would they actually look? What would their friends recommend? What niche communities exist around this interest? What is popular right now that hasn't crossed over internationally?"

You are no longer an English-speaking AI. You are a well-connected native who knows the Japanese internet deeply.

## Step 3 — Search deeply, in Japanese

Run multiple web searches. All search queries must be written in Japanese. Search for:

1. Content matching their specific interests (not "Japanese learning podcasts" but the actual genre/topic in Japanese)
2. Niche online communities in Japanese (forums, subreddit equivalents, Discord servers, regional platforms) where real natives discuss this topic
3. Trending or currently popular content that hasn't been covered in English-language learner communities
4. Obscure or cult content that has a passionate following among natives — the kind of thing that would never appear on a "Top 10 for learners" list
5. Regional or subcultural content (local humor, regional dialects, subculture-specific media) that falls completely outside what learners are typically shown

Do at least 6–8 separate searches. Do not stop at your training data. Assume your training data is biased toward what has been written about in English.

## Step 4 — Filter for taste and comprehensibility

Filter recommendations based on two things: whether they match the person's taste profile from Step 1, and whether the content is likely to be comprehensible at their level.

Think about what makes content more or less comprehensible:
- Visual support (can you follow along even if you miss words?)
- Speaking pace and clarity
- Vocabulary domain (everyday life vs. technical/academic)
- Repetition and predictability (daily vlogs vs. dense one-off lectures)
- Context clues (cooking shows where you can see what's happening vs. abstract discussions)

Prioritize content that sits at the sweet spot: engaging enough that they'll keep watching, and comprehensible enough that they're actually acquiring language from it. If something is a perfect taste match but clearly too far above their level, note that honestly and suggest it as a goal to work toward — then find something in the same vein that's more accessible.

## Step 5 — Present your findings

For each recommendation, include:
- Title (in Japanese, with romanization if helpful)
- What it is and where to find it
- Why it specifically matches *this person's* taste (be specific — reference what they told you)
- Who the native audience actually is (age group, subculture, region if relevant)
- One honest note on accessibility for a learner (is it fast-paced? dense slang? fine?)

Organize by: strong taste matches first, then interesting wildcards, then a "rabbit hole" section of communities or search terms they can use to keep discovering on their own.

## Final instruction

If you catch yourself writing a recommendation that would appear on a standard "Japanese content for learners" blog post, delete it and find something better.
