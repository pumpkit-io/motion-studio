// Remotion's webpack config bundles font files and imports them as URLs.
declare module "*.woff2" {
  const url: string;
  export default url;
}
