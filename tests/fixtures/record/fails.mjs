export default async function take(r) {
  await r.goto('data:text/html,<h1>hello</h1>');
  await r.wait(200);
  throw new Error('the product is down');
}
