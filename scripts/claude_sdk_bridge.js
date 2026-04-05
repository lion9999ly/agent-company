/**
 * Claude Agent SDK Bridge - Python to Claude direct communication
 * Usage: node scripts/claude_sdk_bridge.js <question>
 * Returns: JSON with result
 */
const sdk = require('@anthropic-ai/claude-agent-sdk');

async function queryClaude(question) {
    try {
        // Startup SDK
        const api = await sdk.startup();

        // Send query
        const session = await api.query(question);

        // Iterate messages to get result
        let result = null;
        let assistantContent = [];

        for await (const msg of session.sdkMessages) {
            if (msg.type === 'assistant') {
                // Collect assistant content
                if (msg.message && msg.message.content) {
                    for (const block of msg.message.content) {
                        if (block.type === 'text') {
                            assistantContent.push(block.text);
                        }
                    }
                }
            } else if (msg.type === 'result') {
                // Get final result
                result = {
                    success: true,
                    result: msg.result || null,
                    assistantText: assistantContent.join('\n'),
                    duration_ms: msg.duration_ms,
                    total_cost_usd: msg.total_cost_usd,
                    session_id: msg.session_id,
                    stop_reason: msg.stop_reason
                };
                break;
            }
        }

        await api.close();

        return result || { success: false, error: 'No result received' };
    } catch (e) {
        return { success: false, error: e.message };
    }
}

// Main
const question = process.argv[2];
if (!question) {
    console.log(JSON.stringify({ success: false, error: 'No question provided' }));
    process.exit(1);
}

queryClaude(question).then(result => {
    console.log(JSON.stringify(result));
}).catch(e => {
    console.log(JSON.stringify({ success: false, error: e.message }));
});