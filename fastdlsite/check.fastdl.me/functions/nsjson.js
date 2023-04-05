// SPDX-License-Identifier: WTFPL
// Copyright 2023 rtldg <rtldg@protonmail.com>
// This file is part of fastdl.me (https://github.com/srcwr/maps-cstrike/)

export async function onRequestPost(ctx) {
    const frick = new URL(ctx.request.url);
    frick.pathname = "_thing.json";
    const everything = await (await ctx.env.ASSETS.fetch(frick)).json();

    const json = await ctx.request.json();
    var output = "";
    json.forEach((x, i) => {
        const length = x["Length"];
        const origname = x["Name"].slice(0, -4);
        const name = origname.toLowerCase().replace(".", "_").replace(" ", "_");
        if (!everything[name] || !everything[name].includes(length))
            output += `UNIQUE! ${origname}\n`;
    });
    if (output == "") output = "No unique filename&filesize combinations!\n";
    return new Response(`Comparing against maps from https://fastdl.me\n\n${output}`);
}
