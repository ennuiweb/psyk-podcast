/**
 * RedditStudy Renderer — standalone React prototype
 *
 * Renders Reddit-style thread feeds from thread.json data.
 * This prototype uses hardcoded sample threads drawn from the
 * Personlighedspsykologi course (Weeks 1, 11, 12).
 *
 * In production this component receives `weeklyFeed` as a prop
 * loaded from the portal API: GET /subjects/<slug>/reddit/<lecture_key>/feed.json
 *
 * Run standalone:
 *   npx create-react-app reddit-study-prototype
 *   Replace src/App.js with this file
 *   npm start
 */

import React, { useState } from "react";

// ─── Sample data (3 threads from Personlighedspsykologi) ────────────────────

const SAMPLE_FEED = {
  lecture_key: "W01L1",
  week_topic: "Introduktion til personlighedspsykologi",
  estimated_total_read_time_minutes: 18,
  threads: [
    // Thread 1 — r/explainlikeimfive — W1L1: What is personality?
    {
      thread_id: "W01T1",
      subreddit: "explainlikeimfive",
      subreddit_icon: "🧒",
      subreddit_color: "#0079d3",
      content_metadata: {
        source_readings: ["Grundbog kapitel 1", "Lewis (1999)"],
        learning_objectives: ["Define personality", "Distinguish nomothetic and idiographic approaches"],
        key_terms_embedded: ["nomothetic", "idiographic", "trait", "personality", "self-conscious emotions"],
        concept_cluster: "Introduction to Personality Psychology",
      },
      post: {
        title: "ELI5: Why can't psychologists agree on what 'personality' even means? Is it just made up?",
        body: `I'm starting a personality psychology course and the first lecture already had like 5 different definitions of personality. Some focused on stable traits, some on how people adapt to situations, some on self-concept. My professor said "the definition you choose shapes what counts as evidence" and I nodded but I genuinely don't get what that means. Can someone break this down for me?`,
        author: "bewildered_psych_student",
        author_flair: null,
        upvotes: 4217,
        awards: ["Helpful"],
        timestamp: "11 hours ago",
        flair: "Psychology",
        comment_count: 183,
      },
      comments: [
        {
          id: "c1",
          author: "personality_nerd_42",
          author_flair: "MSc Personality Psychology",
          body: `Great question! The short version: personality is whatever you're trying to *explain*. Different researchers care about different things, so they built different definitions.\n\nHere's the clearest way I've heard it explained:\n\n**Think of personality as a camera lens.** If you use a wide-angle lens, you capture *patterns across many people* — traits like introversion, conscientiousness, agreeableness. You can compare people, run statistics, find that 70% of variance in job performance is explained by a handful of traits. This is the **nomothetic** approach: law-like generalisations across people.\n\nIf you use a close-up lens, you capture *one person in depth* — their unique life history, the specific meaning they give to their experiences, how they make sense of who they are. This is the **idiographic** approach: understanding the individual as an individual.\n\nBoth are valid. But here's why the definition choice matters: if you're nomothetic, you'll use surveys and large datasets. If you're idiographic, you'll use interviews and case studies. The definition literally decides your methods — and different methods find different things. That's what your professor meant.\n\n**The dirty secret of personality psychology:** these two camps have been arguing since the 1930s and neither has "won".`,
          upvotes: 5842,
          awards: ["Gold", "Helpful"],
          timestamp: "10 hours ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c2",
          author: "throwaway_neurostudent",
          author_flair: null,
          body: "Wait, so is personality just traits? Like the Big Five?",
          upvotes: 412,
          awards: [],
          timestamp: "9 hours ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c3",
          author: "personality_nerd_42",
          author_flair: "MSc Personality Psychology",
          body: `The Big Five is *one* model. It's popular because it's cross-culturally replicated and predictively valid for lots of outcomes. But there are psychologists who think traits don't explain *why* someone behaves consistently — just *that* they do.\n\nFor example, the Big Five can tell you someone is high in neuroticism. But it can't tell you what it *feels like* to be that person, or how their early experiences shaped that neuroticism, or whether their neuroticism looks different in different relationships. That's where other approaches (psychodynamic, narrative, sociocultural) come in.`,
          upvotes: 1893,
          awards: [],
          timestamp: "9 hours ago",
          parent_id: "c2",
          depth: 1,
        },
        {
          id: "c4",
          author: "dev_who_reads_psych",
          author_flair: null,
          body: `This maps well to engineering debates about specs vs. emergent behaviour. A spec (trait model) tells you the system's stable parameters. Emergent behaviour approaches say the spec misses everything interesting — the system's behaviour only makes sense in context.\n\nNeither approach builds the whole bridge.`,
          upvotes: 2104,
          awards: ["Wholesome"],
          timestamp: "8 hours ago",
          parent_id: "c1",
          depth: 1,
        },
        {
          id: "c5",
          author: "lewis_reader_2026",
          author_flair: null,
          body: `There's also a developmental angle that gets missed in this nomothetic/idiographic framing. Lewis (1999) argues that what we call "personality" can't be understood without understanding **self-conscious emotions** — things like shame, pride, embarrassment, guilt. These emotions require a self-concept, and they organise how we present ourselves and regulate our behaviour.\n\nSo Lewis would say: personality isn't just traits or stories — it's partly the emotional system that monitors whether you're living up to your own standards. And that system only develops in childhood through specific experiences.\n\nWhich adds a third answer to "what is personality": the organised emotional-motivational system anchored to the self.`,
          upvotes: 1547,
          awards: [],
          timestamp: "7 hours ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c6",
          author: "bewildered_psych_student",
          author_flair: null,
          body: "OP here — okay this is actually clicking now. So the reason we have 5 definitions isn't because psychology is a mess, it's because personality is genuinely multi-dimensional and each definition captures a different dimension?",
          upvotes: 834,
          awards: [],
          timestamp: "6 hours ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c7",
          author: "personality_nerd_42",
          author_flair: "MSc Personality Psychology",
          body: "Exactly. And the key insight your professor was pointing at: whichever dimension you define as *central*, that becomes your object of study, which shapes your methods, which shapes what you find. The definition isn't neutral — it's a theoretical commitment.",
          upvotes: 1204,
          awards: ["Helpful"],
          timestamp: "6 hours ago",
          parent_id: "c6",
          depth: 1,
        },
      ],
      sidebar: {
        key_terms: [
          { term: "Nomothetic", definition: "Approach seeking law-like generalisations across people; uses statistics and large samples" },
          { term: "Idiographic", definition: "Approach focused on understanding the individual in depth; uses case studies and interviews" },
          { term: "Trait", definition: "A relatively stable dimension of individual differences in behaviour and experience" },
          { term: "Self-conscious emotions", definition: "Emotions (shame, pride, guilt, embarrassment) that require a self-concept and monitor self-evaluation" },
        ],
        related_threads: ["W01T2"],
      },
    },

    // Thread 2 — r/changemyview — W11L1: Poststructuralism & subjectivity
    {
      thread_id: "W11T2",
      subreddit: "changemyview",
      subreddit_icon: "💬",
      subreddit_color: "#ef5b00",
      content_metadata: {
        source_readings: ["Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori", "Foucault (1997)"],
        learning_objectives: ["Explain subjectification as an alternative to personality", "Apply Foucault's concept of normalization"],
        key_terms_embedded: ["subjectification", "subject position", "normalization", "discourse", "power-knowledge"],
        concept_cluster: "Poststructuralist Approaches to Personality",
      },
      post: {
        title: "CMV: Foucault's concept of 'subjectification' is just a pretentious rebranding of socialisation, and personality psychology doesn't need it",
        body: `I've been reading poststructuralist takes on personality for my course and I'm not convinced they add anything. The argument seems to be: society shapes who we become through norms and institutions. But we already knew that — it's called socialisation, it's been in the sociological literature since Durkheim, and it doesn't require abandoning the concept of a persistent self.\n\nFoucault's "subjectification" just seems to add political vocabulary (power, discourse, resistance) to what is basically "social influence". Change my view.`,
        author: "empiricist_psych_bro",
        author_flair: "Undergraduate • Quantitative Methods",
        upvotes: 1843,
        awards: [],
        timestamp: "2 days ago",
        flair: null,
        comment_count: 94,
      },
      comments: [
        {
          id: "c1",
          author: "poststructural_pers",
          author_flair: "PhD candidate, Critical Psychology",
          body: `Δ You're right that there's overlap with socialisation — but the key difference is in what subjectification explains that socialisation doesn't.\n\nSocialisation says: external norms are internalised by a pre-existing individual. There's a "you" that receives the norms.\n\nSubjectification says: **the very sense of being a coherent individual is itself produced by the process**. There isn't a "you" prior to subjectification — the subject position is what makes self-experience possible.\n\nThis is the Grundbog chapter's central claim: personality is not a property of a pre-existing self but an ongoing effect of positioning within discourse. The self that "has" personality traits is itself constituted by historically and politically organised subject positions.\n\nWhy does this matter practically? Because if personality is constituted in discourse, then changing personality isn't a matter of individual will — it requires changing the discursive conditions that make certain subject positions available. That's a very different intervention target than CBT.`,
          upvotes: 2341,
          awards: ["Silver"],
          timestamp: "2 days ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c2",
          author: "empiricist_psych_bro",
          author_flair: "Undergraduate • Quantitative Methods",
          body: "Δ Okay, the 'there isn't a you prior to subjectification' point is actually the crux I was missing. I was reading it as socialisation because I was assuming a pre-existing subject. If the claim is that subjecthood itself is constructed, that's a genuinely different ontological claim, not just vocabulary. Granting this delta.",
          upvotes: 987,
          awards: [],
          timestamp: "2 days ago",
          parent_id: "c1",
          depth: 1,
        },
        {
          id: "c3",
          author: "foucault_skeptic_99",
          author_flair: null,
          body: `I want to push back on the practical implications here. Subjectification theory is great for critique but almost useless for clinical intervention. If there's no stable self, who are you treating? The therapy literature is built on the assumption that there is a persistent person across sessions with coherent problems that can be addressed.\n\nA therapist can't work with "your distress is an effect of discursive positioning". They need something actionable.`,
          upvotes: 1204,
          awards: [],
          timestamp: "1 day ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c4",
          author: "poststructural_pers",
          author_flair: "PhD candidate, Critical Psychology",
          body: `That's a real tension and the field hasn't resolved it cleanly. Narrative therapy (White & Epston) is probably the most developed attempt to do clinical work *from* a poststructuralist premise — externalizing the problem, examining which cultural discourses produced it, opening alternative story lines.\n\nBut you're right that it doesn't work well for symptom-focused interventions. The honest position is: different ontological frameworks are useful for different questions. Subjectification is a better framework for understanding how diagnostic categories like "borderline personality disorder" shape (and pathologise) certain subject positions, not for treating the person in front of you right now.`,
          upvotes: 1567,
          awards: ["Helpful"],
          timestamp: "1 day ago",
          parent_id: "c3",
          depth: 1,
        },
        {
          id: "c5",
          author: "normalization_nerd",
          author_flair: null,
          body: `The Foucault piece also has a very specific point about **normalisation** that gets lost when people treat it as just "social influence". Normalization isn't about conformity pressure — it's about how a particular distribution (the normal curve) becomes a regulatory ideal. To be "normal" is to occupy the densest part of a distribution, and that distribution is itself historically produced.\n\nSo when personality psychology uses standard deviations, it's not just describing — it's participating in a normative apparatus that defines what counts as a healthy, functional self. That's Foucault's point. The measurement tool is also a governance tool.`,
          upvotes: 1893,
          awards: ["Gold"],
          timestamp: "23 hours ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c6",
          author: "empiricist_psych_bro",
          author_flair: "Undergraduate • Quantitative Methods",
          body: "The normalisation point genuinely surprised me. I hadn't thought about the normal distribution as a normative concept — just as a mathematical description. That reframe is doing a lot of work.",
          upvotes: 543,
          awards: [],
          timestamp: "22 hours ago",
          parent_id: "c5",
          depth: 1,
        },
      ],
      sidebar: {
        key_terms: [
          { term: "Subjectification", definition: "The process through which individuals become subjects — not just shaped by social norms, but constituted as selves through them" },
          { term: "Subject position", definition: "A location within a discourse that defines what it is possible to say, do, and be" },
          { term: "Normalization", definition: "Foucault: the production of 'the normal' as a regulatory ideal through measurement and comparison" },
          { term: "Discourse", definition: "A system of knowledge/language that defines what can be thought and said within a domain" },
          { term: "Power-knowledge", definition: "Foucault's term for the inseparability of power relations and knowledge production" },
        ],
        related_threads: ["W11T1", "W12T1"],
      },
    },

    // Thread 3 — r/AmItheAsshole — W12L1: Narrative identity and therapy
    {
      thread_id: "W12T1",
      subreddit: "AmItheAsshole",
      subreddit_icon: "⚖️",
      subreddit_color: "#ff4500",
      content_metadata: {
        source_readings: ["McAdams & Pals (2006)", "Grundbog kapitel 9 - Narrative teorier", "Bruner (1999)"],
        learning_objectives: ["Explain narrative identity", "Distinguish between paradigmatic and narrative modes of thought (Bruner)", "Apply McAdams' personality framework"],
        key_terms_embedded: ["narrative identity", "life story", "paradigmatic mode", "narrative mode", "redemption sequence", "contamination sequence"],
        concept_cluster: "Narrative Approaches to Personality",
      },
      post: {
        title: "AITA for telling my therapist their 'life story' approach was unscientific and refusing to engage with the exercises?",
        body: `I (24M) have been seeing a therapist for about 6 months for anxiety and general directionlessness. She uses narrative therapy — a lot of "tell me about a pivotal moment", "how does that fit your story of who you are", "what kind of person does this chapter suggest you're becoming".\n\nI'm doing a psychology degree and I know narrative approaches are hard to operationalise. You can't run an RCT on "does someone's life story become more coherent". I told her I thought we were wasting time with vague storytelling when I could be doing evidence-based CBT exercises.\n\nShe was professional about it but clearly frustrated. My friend thinks I was being a jerk. AITA?`,
        author: "anxious_psych_student",
        author_flair: null,
        upvotes: 12847,
        awards: ["Wholesome", "Silver"],
        timestamp: "5 days ago",
        flair: null,
        comment_count: 641,
      },
      comments: [
        {
          id: "c1",
          author: "narrative_therapist_irl",
          author_flair: "Therapist (LMFT)",
          body: `NTA for having concerns, but I think you have some wrong assumptions about the evidence base.\n\nMcAdams and colleagues have been studying narrative identity empirically since the 1980s. McAdams & Pals (2006) lays out a personality framework where life stories are the *third level* of personality — below traits (level 1) and characteristic adaptations like goals, motives, schemas (level 2), but just as important for understanding the full person.\n\nOn the empirical side: research consistently shows that the *structure* of people's life narratives predicts psychological wellbeing. Specifically, people who tell "redemption sequences" (bad thing happened → I grew from it) show higher wellbeing and lower depression than people who tell "contamination sequences" (good thing happened → it was ruined). These are quantifiable coding categories applied to interview transcripts. That's measurable.\n\nSo when your therapist asks about pivotal moments, she's not doing vague storytelling — she's assessing whether your narrative structure is redemptive or contaminating, and trying to help you rework contamination sequences.\n\nYTA for dismissing this without checking what the evidence actually is.`,
          upvotes: 18432,
          awards: ["Helpful", "Gold"],
          timestamp: "5 days ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c2",
          author: "rct_purist",
          author_flair: null,
          body: "But redemption sequences being correlated with wellbeing doesn't mean *changing* someone's narrative causes wellbeing to improve. Correlation ≠ causation. The RCT question is still valid.",
          upvotes: 4321,
          awards: [],
          timestamp: "5 days ago",
          parent_id: "c1",
          depth: 1,
        },
        {
          id: "c3",
          author: "narrative_therapist_irl",
          author_flair: "Therapist (LMFT)",
          body: "That's fair and the field acknowledges it. Longitudinal studies show that narrative change precedes wellbeing change (not the reverse) in several samples, which is at least consistent with causation. But yes, it's not as clean as a pill trial. No therapy modality is — including CBT, which has its own replication issues.",
          upvotes: 3102,
          awards: [],
          timestamp: "5 days ago",
          parent_id: "c2",
          depth: 2,
        },
        {
          id: "c4",
          author: "bruner_fan_account",
          author_flair: "Developmental Psych PhD",
          body: `The framing of "narrative vs. scientific" in OP's complaint is actually a false dichotomy that Bruner (1999) addressed directly.\n\nBruner distinguished between two irreducible modes of thought:\n- **Paradigmatic mode**: logical, formal, seeks truth via proof and falsification. Science operates here.\n- **Narrative mode**: concerned with human intention, context, and meaning. It evaluates stories by their *verisimilitude* (felt truth) rather than formal proof.\n\nBruner's point is that neither mode reduces to the other. You cannot evaluate a life story using the same criteria as a hypothesis test — not because narrative is inferior, but because it is *constitutively different*. A life narrative is not a claim about the world that can be falsified. It is a meaning-making structure.\n\nOP is applying paradigmatic evaluation criteria to something that operates in the narrative domain. That's a category error, not a methodological insight.`,
          upvotes: 8234,
          awards: ["Best Comment", "Helpful"],
          timestamp: "4 days ago",
          parent_id: null,
          depth: 0,
        },
        {
          id: "c5",
          author: "anxious_psych_student",
          author_flair: null,
          body: "OP here. The Bruner point about two irreducible modes is hitting differently than I expected. I think I genuinely was applying the wrong evaluation standard. I still don't fully know if narrative therapy is the right fit for me personally, but calling it 'unscientific' was probably wrong — it's operating in a different but valid epistemic register.",
          upvotes: 6102,
          awards: ["Wholesome"],
          timestamp: "4 days ago",
          parent_id: "c4",
          depth: 1,
        },
        {
          id: "c6",
          author: "actual_therapy_veteran",
          author_flair: null,
          body: `NTA on the questioning, but YTA on the execution. Therapists hear "your approach is unscientific" as "I don't trust you", not as a methodological note. The therapeutic alliance is itself evidence-based — a damaged alliance predicts worse outcomes across all modalities. You may have accidentally undermined the thing that makes any therapy work.\n\nThe move would have been: "I've been reading about narrative therapy and I'm curious how you'd respond to [specific concern]." Same intellectual content, very different relational message.`,
          upvotes: 11203,
          awards: ["Silver"],
          timestamp: "3 days ago",
          parent_id: null,
          depth: 0,
        },
      ],
      sidebar: {
        key_terms: [
          { term: "Narrative identity", definition: "The internalized life story that a person constructs to give their life a sense of unity and purpose across time" },
          { term: "Life story", definition: "McAdams: the third level of personality — a personal narrative integrating past, present, and anticipated future" },
          { term: "Redemption sequence", definition: "Narrative structure: bad event → growth or positive meaning. Predicts higher wellbeing" },
          { term: "Contamination sequence", definition: "Narrative structure: good event → ruined or tainted outcome. Predicts lower wellbeing and depression" },
          { term: "Paradigmatic mode", definition: "Bruner: logical-formal thinking that seeks truth via proof. The mode of science" },
          { term: "Narrative mode", definition: "Bruner: meaning-making thinking that evaluates by verisimilitude (felt truth), not formal proof. Irreducible to paradigmatic mode" },
        ],
        related_threads: ["W11T2"],
      },
    },
  ],
};

// ─── Comment Component ──────────────────────────────────────────────────────

function Comment({ comment, allComments, depth = 0 }) {
  const [collapsed, setCollapsed] = useState(false);
  const children = allComments.filter((c) => c.parent_id === comment.id);

  const depthColors = [
    "#0079d3", "#ff4500", "#46d160", "#ff585b", "#9c59d1", "#db0064", "#46d160",
  ];
  const borderColor = depthColors[depth % depthColors.length];

  const formatUpvotes = (n) => {
    if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
    return `${n}`;
  };

  return (
    <div
      style={{
        marginLeft: depth > 0 ? 16 : 0,
        borderLeft: depth > 0 ? `2px solid ${borderColor}20` : "none",
        paddingLeft: depth > 0 ? 12 : 0,
        marginTop: 8,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        {/* Thread line click target */}
        <div
          onClick={() => setCollapsed(!collapsed)}
          style={{
            width: 2,
            minHeight: collapsed ? 20 : "100%",
            background: depth === 0 ? "#edeff1" : `${borderColor}30`,
            cursor: "pointer",
            borderRadius: 2,
            flexShrink: 0,
            alignSelf: "stretch",
          }}
        />
        <div style={{ flex: 1 }}>
          {/* Comment header */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 4 }}>
            <span
              style={{
                fontWeight: 700,
                fontSize: 12,
                color: comment.author_flair ? "#0079d3" : "#1c1c1c",
                cursor: "pointer",
              }}
            >
              u/{comment.author}
            </span>
            {comment.author_flair && (
              <span
                style={{
                  fontSize: 11,
                  color: "#878a8c",
                  background: "#f6f7f8",
                  padding: "1px 6px",
                  borderRadius: 2,
                }}
              >
                {comment.author_flair}
              </span>
            )}
            <span style={{ fontSize: 12, color: "#878a8c" }}>
              {formatUpvotes(comment.upvotes)} points
            </span>
            <span style={{ fontSize: 12, color: "#878a8c" }}>•</span>
            <span style={{ fontSize: 12, color: "#878a8c" }}>{comment.timestamp}</span>
            {comment.awards.map((award) => (
              <span
                key={award}
                style={{
                  fontSize: 10,
                  background: award === "Gold" ? "#ffd700" : award === "Silver" ? "#c0c0c0" : "#ff8c00",
                  color: "#fff",
                  padding: "1px 5px",
                  borderRadius: 10,
                  fontWeight: 600,
                }}
              >
                {award}
              </span>
            ))}
          </div>

          {/* Comment body */}
          {!collapsed && (
            <div style={{ fontSize: 14, lineHeight: 1.6, color: "#1c1c1c" }}>
              <MarkdownText text={comment.body} />
            </div>
          )}

          {/* Comment actions */}
          {!collapsed && (
            <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
              <button
                onClick={() => setCollapsed(true)}
                style={actionBtnStyle}
              >
                collapse
              </button>
              <span style={{ fontSize: 12, color: "#878a8c", cursor: "pointer" }}>reply</span>
              <span style={{ fontSize: 12, color: "#878a8c", cursor: "pointer" }}>share</span>
            </div>
          )}

          {/* Recursive children */}
          {!collapsed &&
            children.map((child) => (
              <Comment
                key={child.id}
                comment={child}
                allComments={allComments}
                depth={depth + 1}
              />
            ))}
        </div>
      </div>
    </div>
  );
}

// ─── Minimal markdown renderer ──────────────────────────────────────────────

function MarkdownText({ text }) {
  const lines = text.split("\n");
  return (
    <div>
      {lines.map((line, i) => {
        // Bold: **text**
        const parts = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return <strong key={j}>{part.slice(2, -2)}</strong>;
          }
          return part;
        });
        if (line === "") return <br key={i} />;
        if (line.startsWith("- ")) {
          return (
            <li key={i} style={{ marginLeft: 20, marginBottom: 2 }}>
              {line.slice(2).split(/(\*\*[^*]+\*\*)/g).map((p, j) =>
                p.startsWith("**") && p.endsWith("**") ? <strong key={j}>{p.slice(2, -2)}</strong> : p
              )}
            </li>
          );
        }
        return <p key={i} style={{ margin: "4px 0" }}>{parts}</p>;
      })}
    </div>
  );
}

// ─── Thread Card ─────────────────────────────────────────────────────────────

function ThreadCard({ thread, isActive, onClick }) {
  const formatUpvotes = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
  return (
    <div
      onClick={onClick}
      style={{
        background: isActive ? "#f6f7f8" : "#fff",
        border: `1px solid ${isActive ? "#0079d3" : "#ccc"}`,
        borderRadius: 4,
        padding: "8px 12px",
        cursor: "pointer",
        marginBottom: 4,
        display: "flex",
        gap: 8,
        alignItems: "flex-start",
      }}
    >
      <span style={{ fontSize: 18 }}>{thread.subreddit_icon}</span>
      <div>
        <div style={{ fontSize: 11, color: "#878a8c", marginBottom: 2 }}>
          r/{thread.subreddit}
        </div>
        <div style={{ fontSize: 13, fontWeight: 500, color: "#1c1c1c", lineHeight: 1.3 }}>
          {thread.post.title.length > 80
            ? thread.post.title.slice(0, 80) + "…"
            : thread.post.title}
        </div>
        <div style={{ fontSize: 11, color: "#878a8c", marginTop: 3 }}>
          ▲ {formatUpvotes(thread.post.upvotes)} • {thread.post.comment_count} comments
        </div>
      </div>
    </div>
  );
}

// ─── Full Thread View ─────────────────────────────────────────────────────────

function ThreadView({ thread }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const formatUpvotes = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);
  const topLevelComments = thread.comments.filter((c) => c.parent_id === null);

  return (
    <div style={{ display: "flex", gap: 24 }}>
      {/* Main thread */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Subreddit header */}
        <div
          style={{
            background: thread.subreddit_color,
            color: "#fff",
            padding: "8px 16px",
            borderRadius: "4px 4px 0 0",
            fontSize: 13,
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span>{thread.subreddit_icon}</span>
          r/{thread.subreddit}
        </div>

        {/* Post */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #ccc",
            borderTop: "none",
            padding: 16,
          }}
        >
          {/* Vote + post */}
          <div style={{ display: "flex", gap: 12 }}>
            {/* Vote widget */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 2,
                minWidth: 32,
              }}
            >
              <span style={{ fontSize: 18, color: "#ff4500", cursor: "pointer" }}>▲</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#ff4500" }}>
                {formatUpvotes(thread.post.upvotes)}
              </span>
              <span style={{ fontSize: 18, color: "#9b9b9b", cursor: "pointer" }}>▼</span>
            </div>

            {/* Post content */}
            <div style={{ flex: 1 }}>
              {thread.post.flair && (
                <span
                  style={{
                    fontSize: 11,
                    background: `${thread.subreddit_color}20`,
                    color: thread.subreddit_color,
                    padding: "2px 8px",
                    borderRadius: 2,
                    fontWeight: 700,
                    marginBottom: 6,
                    display: "inline-block",
                  }}
                >
                  {thread.post.flair}
                </span>
              )}
              <h2
                style={{
                  fontSize: 18,
                  fontWeight: 500,
                  color: "#1c1c1c",
                  margin: "0 0 8px",
                  lineHeight: 1.4,
                }}
              >
                {thread.post.title}
              </h2>
              <div style={{ fontSize: 11, color: "#878a8c", marginBottom: 12 }}>
                Posted by{" "}
                <span style={{ fontWeight: 600 }}>u/{thread.post.author}</span>
                {thread.post.author_flair && (
                  <span
                    style={{
                      marginLeft: 6,
                      background: "#f6f7f8",
                      padding: "1px 6px",
                      borderRadius: 2,
                    }}
                  >
                    {thread.post.author_flair}
                  </span>
                )}{" "}
                • {thread.post.timestamp}
                {thread.post.awards.map((a) => (
                  <span
                    key={a}
                    style={{
                      marginLeft: 6,
                      fontSize: 10,
                      background: a === "Gold" ? "#ffd700" : "#ff8c00",
                      color: "#fff",
                      padding: "1px 5px",
                      borderRadius: 10,
                      fontWeight: 600,
                    }}
                  >
                    {a}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: "#1c1c1c" }}>
                <MarkdownText text={thread.post.body} />
              </div>
              <div style={{ display: "flex", gap: 16, marginTop: 12 }}>
                <span style={{ fontSize: 12, color: "#878a8c" }}>
                  💬 {thread.post.comment_count} Comments
                </span>
                <span style={{ fontSize: 12, color: "#878a8c", cursor: "pointer" }}>
                  🔗 Share
                </span>
                <span style={{ fontSize: 12, color: "#878a8c", cursor: "pointer" }}>
                  ⭐ Save
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Comments */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #ccc",
            borderTop: "1px solid #edeff1",
            padding: 16,
          }}
        >
          <div style={{ fontSize: 13, color: "#1c1c1c", fontWeight: 600, marginBottom: 12 }}>
            Top Comments
          </div>
          {topLevelComments.map((comment) => (
            <Comment
              key={comment.id}
              comment={comment}
              allComments={thread.comments}
              depth={0}
            />
          ))}
        </div>
      </div>

      {/* Sidebar */}
      <div style={{ width: 280, flexShrink: 0 }}>
        {/* Key terms */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #ccc",
            borderRadius: 4,
            overflow: "hidden",
            marginBottom: 12,
          }}
        >
          <div
            style={{
              background: thread.subreddit_color,
              color: "#fff",
              padding: "8px 12px",
              fontSize: 13,
              fontWeight: 700,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              cursor: "pointer",
            }}
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            📖 Key Terms
            <span>{sidebarOpen ? "▲" : "▼"}</span>
          </div>
          {sidebarOpen && (
            <div style={{ padding: 12 }}>
              {thread.sidebar.key_terms.map((kt) => (
                <div key={kt.term} style={{ marginBottom: 10 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: "#1c1c1c",
                      marginBottom: 2,
                    }}
                  >
                    {kt.term}
                  </div>
                  <div style={{ fontSize: 12, color: "#4a4a4a", lineHeight: 1.5 }}>
                    {kt.definition}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Learning objectives metadata */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #ccc",
            borderRadius: 4,
            padding: 12,
            fontSize: 12,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 8, color: "#1c1c1c" }}>
            📚 About This Thread
          </div>
          <div style={{ color: "#4a4a4a", marginBottom: 6 }}>
            <strong>Readings:</strong> {thread.content_metadata.source_readings.join(", ")}
          </div>
          <div style={{ color: "#4a4a4a", marginBottom: 6 }}>
            <strong>Concept:</strong> {thread.content_metadata.concept_cluster}
          </div>
          <div style={{ color: "#4a4a4a" }}>
            <strong>Bloom levels:</strong> {thread.content_metadata.bloom_levels.join(", ")}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Action button style ─────────────────────────────────────────────────────

const actionBtnStyle = {
  fontSize: 12,
  color: "#878a8c",
  background: "none",
  border: "none",
  cursor: "pointer",
  padding: 0,
  fontWeight: 700,
};

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [activeThreadId, setActiveThreadId] = useState(SAMPLE_FEED.threads[0].thread_id);
  const activeThread = SAMPLE_FEED.threads.find((t) => t.thread_id === activeThreadId);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#dae0e6",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif",
      }}
    >
      {/* Top nav bar */}
      <div
        style={{
          background: "#fff",
          borderBottom: "1px solid #edeff1",
          padding: "8px 24px",
          display: "flex",
          alignItems: "center",
          gap: 24,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ fontSize: 18, fontWeight: 800, color: "#ff4500" }}>reddit</div>
        <div style={{ color: "#1c1c1c", fontSize: 14, fontWeight: 600 }}>
          📚 {SAMPLE_FEED.week_topic}
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#878a8c" }}>
          ~{SAMPLE_FEED.estimated_total_read_time_minutes} min read •{" "}
          {SAMPLE_FEED.threads.length} threads
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 24px", display: "flex", gap: 20 }}>
        {/* Thread list sidebar */}
        <div style={{ width: 260, flexShrink: 0 }}>
          <div
            style={{
              background: "#fff",
              border: "1px solid #ccc",
              borderRadius: 4,
              padding: 12,
              marginBottom: 12,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700, color: "#1c1c1c", marginBottom: 8 }}>
              Week Feed
            </div>
            {SAMPLE_FEED.threads.map((thread) => (
              <ThreadCard
                key={thread.thread_id}
                thread={thread}
                isActive={thread.thread_id === activeThreadId}
                onClick={() => setActiveThreadId(thread.thread_id)}
              />
            ))}
          </div>
        </div>

        {/* Active thread */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {activeThread && <ThreadView thread={activeThread} />}
        </div>
      </div>
    </div>
  );
}
