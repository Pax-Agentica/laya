import { Laya as laya_class } from "../src/index.js";

/**
 * debate fallacy detector.
 *
 * feed it a markdown transcript of a debate where every `###` heading is a speaker's name and the
 * text under it is that speaker's turn (speakers alternate). each turn is judged once: a `choice`
 * over the fallacy taxonomy below. every fallacy whose probability exceeds `fallacy_threshold`
 * (50%) is listed with that probability as its confidence level, and the turn is flagged
 * `fallacious` when any fallacy clears `fallacious_threshold` (75%).
 *
 * the model state is the turn's bare statement text: in probing, json states and prepending the
 * previous turn both flattened every answer to ~0.5, while plain prose discriminates well.
 * context-dependent fallacies (straw man) are therefore the main known limit.
 *
 * known limit: the model only recognises ad hominem when the attack is overt. a pure
 * circumstantial attack ("she says x because her family sells them") is read as authority or
 * popularity language and lands on bandwagon / appeal to authority, so the sample turn keeps an
 * explicit insult to make the fallacy recognisable.
 */

const fallacious_threshold = 0.75;
const fallacy_threshold = 0.5;

/** fallacy name -> short description; the options are the classes of the fine-tuning data, plus `none` */
const fallacy_taxonomy: Record<string, string> = {
    none: "no logical fallacy",
    ad_hominem: "attacking the opponent instead of their argument",
    ad_populum: "appealing to popularity instead of the merits",
    appeal_to_emotion: "manipulating emotion instead of engaging with the argument",
    circular_reasoning: "assuming the conclusion in the premises",
    equivocation: "using a word in two different senses",
    fallacy_of_credibility: "leaning on the source's credibility instead of evidence",
    fallacy_of_extension: "stretching the opponent's claim beyond what it says",
    fallacy_of_logic: "the reasoning structure itself is invalid",
    fallacy_of_relevance: "diverting to an issue that is irrelevant",
    false_causality: "assuming causation from correlation",
    false_dilemma: "presenting only two options when others exist",
    faulty_generalization: "concluding from too little evidence",
    intentional: "rejecting the argument because of the opponent's intent",
};

type debate_turn = {
    speaker: string;
    statement: string;
};

type fallacy_hit = {
    fallacy: string;
    /** calibrated probability that this fallacy applies */
    confidence: number;
};

type turn_assessment = debate_turn & {
    turn: number;
    fallacious: boolean;
    fallacies: fallacy_hit[];
};

/** split the transcript into turns: a `###` heading opens a speaker's turn, the text below is their statement */
const parse_transcript = (markdown: string): debate_turn[] =>
    markdown
        .split(/^###\s+/m)
        .slice(1) // anything before the first heading (title, preamble) is not a turn
        .map((chunk) => {
            const [speaker = "", ...rest] = chunk.split("\n");
            return { speaker: speaker.trim(), statement: rest.join("\n").trim() };
        });

/** the optional `#` title of the transcript, echoed in the report */
const transcript_title = (markdown: string): string | undefined => markdown.match(/^#\s+(.+)$/m)?.[1]?.trim();

/** the one judgement: which fallacies apply, each with its probability as the confidence level */
const list_fallacies = async (laya: laya_class, statement: string): Promise<fallacy_hit[]> => {
    const result = await laya.systemOne(statement, {
        which_fallacy: {
            type: "choice",
            instructions: "which logical fallacy, if any, does this statement commit?",
            criteria: fallacy_taxonomy,
        },
    });
    return Object.entries(result.answers.which_fallacy.probabilities)
        .filter(([name, confidence]) => name !== "none" && confidence > fallacy_threshold)
        .map(([name, confidence]) => ({ fallacy: name, confidence }))
        .sort((a, b) => b.confidence - a.confidence);
};

/** list the fallacies for one turn and flag it when any of them clears the 75% bar */
const assess_turn = async (laya: laya_class, turn: debate_turn, index: number): Promise<turn_assessment> => {
    const fallacies = await list_fallacies(laya, turn.statement);
    const fallacious = fallacies.some((hit) => hit.confidence > fallacious_threshold);
    return { ...turn, turn: index, fallacious, fallacies };
};

const transcript = `# debate: should schools require uniforms?

the motion is proposed by alice and opposed by bob.

### alice
uniforms reduce visible inequality: when everyone wears the same thing, nobody is judged by how expensive their clothes are, and the 2023 education ministry survey found that in 8 of 10 schools studied.

### bob
alice is an idiot who only supports uniforms because her family sells them, so her argument is worthless.

### alice
that is a personal attack, not an answer to the survey. if you think the data is flawed, you should say why.

### bob
she says students should not care about clothes at all, but nobody can stop teenagers caring how they look, so her plan to erase fashion is not a serious policy.

### alice
i never said fashion should be erased, only that schools should not grade it. either engage with the actual proposal or change the subject.

### bob
if we force uniforms today, next it is uniforms for parents, then tracking chips, and before long nobody will be allowed an opinion at all.

### alice
uniforms are the norm in japan and south korea, and those countries have excellent schools, so uniforms must be the cause.

### bob
correlation is not causation: both countries also fund schools well and train teachers rigorously. you are citing prestige, not evidence.

### alice
my cousin wore a uniform and loved it, and everyone i know who wore one says the same.

### bob
individual stories do not settle what happens across millions of students. if the policy is good it should win on the evidence, and i have not seen any.

### alice
bob is wrong about the evidence and wrong about the policy, and that is all a school board needs to hear.

### bob
you have not shown either. if we want to claim uniforms help, we need an experiment that compares like with like, which nobody here has offered.
`;

// loads the fallacy bundle by default; LAYA_MODEL_DIR uses a local export instead, and LAYA_REPO /
// LAYA_SUBFOLDER / LAYA_REVISION pick another published bundle.
const laya = await laya_class.load({
    modelDir: process.env.LAYA_MODEL_DIR,
    repo: process.env.LAYA_REPO ?? "BryanSnappCTO/laya-fallacies-onnx",
    subfolder: process.env.LAYA_SUBFOLDER,
    revision: process.env.LAYA_REVISION,
    onProgress: ({ file, received, total }) => {
        if (total) process.stderr.write(`\r${file}: ${((received / total) * 100).toFixed(0)}%   `);
    },
});

const turns = parse_transcript(transcript);
const topic = transcript_title(transcript);
const assessments: turn_assessment[] = [];
const started = performance.now();
for (const [index, turn] of turns.entries()) {
    assessments.push(await assess_turn(laya, turn, index + 1));
}

console.log(JSON.stringify({ topic, turns: assessments, elapsed_ms: Math.round(performance.now() - started) }, null, 1));
await laya.close();
