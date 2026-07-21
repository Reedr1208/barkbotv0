import React from 'react';
import { ScrollViewStyleReset } from 'expo-router/html';

export default function HTML({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
        
        {/* SEO Metatags that dog_meta.py replaces */}
        <title>ChattyHound – Chat With Adoptable Shelter Dogs 🐾</title>
        <meta name="description" content="🐶 Chat with adoptable shelter dogs! Discover their quirks, personality, and needs in real-time, build your match profile, and find your new best friend who fits your life." />
        <link rel="canonical" href="https://chattyhound.com/" />

        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://chattyhound.com/" />
        <meta property="og:title" content="ChattyHound – Chat With Adoptable Shelter Dogs 🐾" />
        <meta property="og:description" content="🐶 Chat with adoptable shelter dogs! Discover their quirks, personality, and needs in real-time, build your match profile, and find your new best friend who fits your life." />
        <meta property="og:image" content="https://chattyhound.com/chattyhound_og.png" />
        <meta property="og:image:secure_url" content="https://chattyhound.com/chattyhound_og.png" />
        <meta property="og:image:type" content="image/png" />
        <meta property="og:image:width" content="1024" />
        <meta property="og:image:height" content="1024" />

        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:url" content="https://chattyhound.com/" />
        <meta property="twitter:title" content="ChattyHound – Chat With Adoptable Shelter Dogs 🐾" />
        <meta property="twitter:description" content="🐶 Chat with adoptable shelter dogs! Discover their quirks, personality, and needs in real-time, build your match profile, and find your new best friend who fits your life." />
        <meta property="twitter:image" content="https://chattyhound.com/chattyhound_og.png" />

        <link rel="icon" href="/favicon_dog.png" type="image/png" />

        {/* FullStory Snippet */}
        <script dangerouslySetInnerHTML={{ __html: `
          window['_fs_host'] = 'fullstory.com';
          window['_fs_script'] = 'edge.fullstory.com/s/fs.js';
          window['_fs_org'] = 'ZKPBZ';
          window['_fs_namespace'] = 'FS';
          !function(m,n,e,t,l,o,g,y){var s,f,a=function(h){
          return!(h in m)||(m.console&&m.console.log&&m.console.log('FullStory namespace conflict. Please set window["_fs_namespace"].'),!1)}(e)
          ;function p(b){var h,d=[];function j(){h&&(d.forEach((function(b){var d;try{d=b[h[0]]&&b[h[0]](h[1])}catch(h){return void(b[3]&&b[3](h))}
          d&&d.then?d.then(b[2],b[3]):b[2]&&b[2](d)})),d.length=0)}function r(b){return function(d){h||(h=[b,d],j())}}return b(r(0),r(1)),{
          then:function(b,h){return p((function(r,i){d.push([b,h,r,i]),j()}))}}}a&&(g=m[e]=function(){var b=function(b,d,j,r){function i(i,c){
          h(b,d,j,i,c,r)}r=r||2;var c,u=/Async$/;return u.test(b)?(b=b.replace(u,""),"function"==typeof Promise?new Promise(i):p(i)):h(b,d,j,c,c,r)}
          ;function h(h,d,j,r,i,c){return b._api?b._api(h,d,j,r,i,c):(b.q&&b.q.push([h,d,j,r,i,c]),null)}return b.q=[],b}(),y=function(b){function h(h){
          "function"==typeof h[4]&&h[4](new Error(b))}var d=g.q;if(d){for(var j=0;j<d.length;j++)h(d[j]);d.length=0,d.push=h}},function(){
          (o=n.createElement(t)).async=!0,o.crossOrigin="anonymous",o.src="https://"+l,o.onerror=function(){y("Error loading "+l)}
          ;var b=n.getElementsByTagName(t)[0];b&&b.parentNode?b.parentNode.insertBefore(o,b):n.head.appendChild(o)}(),function(){function b(){}
          function h(b,h,d){g(b,h,d,1)}function d(b,d,j){h("setProperties",{type:b,properties:d},j)}function j(b,h){d("user",b,h)}function r(b,h,d){j({
          uid:b},d),h&&j(h,d)}g.identify=r,g.setUserVars=j,g.identifyAccount=b,g.clearUserCookie=b,g.setVars=d,g.event=function(b,d,j){h("trackEvent",{
          name:b,properties:d},j)},g.anonymize=function(){r(!1)},g.shutdown=function(){h("shutdown")},g.restart=function(){h("restart")},
          g.log=function(b,d){h("log",{level:b,msg:d})},g.consent=function(b){h("setIdentity",{consent:!arguments.length||b})}}(),s="fetch",
          f="XMLHttpRequest",g._w={},g._w[f]=m[f],g._w[s]=m[s],m[s]&&(m[s]=function(){return g._w[s].apply(this,arguments)}),g._v="2.0.0")
          }(window,document,window._fs_namespace,"script",window._fs_script);
        `}} />

        {/* Google Tag (gtag.js) */}
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-4GRL2M87SZ" />
        <script dangerouslySetInnerHTML={{ __html: `
          window.dataLayer = window.dataLayer || [];
          function gtag() { dataLayer.push(arguments); }
          gtag('js', new Date());
          gtag('config', 'G-4GRL2M87SZ');
        `}} />

        <ScrollViewStyleReset />
        
        <style dangerouslySetInnerHTML={{ __html: `
          html, body {
            background-color: #020617; /* colors.slate950 */
          }
        `}} />
      </head>
      <body>{children}</body>
    </html>
  );
}
