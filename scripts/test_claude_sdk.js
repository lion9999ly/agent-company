const sdk = require('@anthropic-ai/claude-agent-sdk');

async function test() {
    try {
        console.log('Starting SDK...');
        const api = await sdk.startup();
        console.log('SDK started, sending query...');
        const result = await api.query('What is 2+2? Reply with just the number.');
        console.log('Result:', JSON.stringify(result, null, 2));
        await api.close();
        console.log('Done');
    } catch (e) {
        console.error('Error:', e.message);
        console.error('Stack:', e.stack);
    }
}

test();