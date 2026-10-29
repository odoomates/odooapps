import { Component, markup, onWillStart, onWillUnmount, proxy, usePlugin, useProps } from "@odoo/owl";
import { DebugModePlugin } from "@web/core/debug_mode_plugin";
import { _t } from "@web/core/l10n/translation";
import { rpcBus } from "@web/core/network/rpc";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "academy.progress";

/**
 * The Academy: the courses, then a course step by step. Each step explains,
 * shows the files of the learner's module (new lines marked), and offers the
 * actions of the chosen mode: Code it (write, install, check) or Build it
 * live (build, undo). See it opens in Odoo what the step made.
 */
export class Academy extends Component {
    static template = "om_academy.Academy";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.effect = useService("effect");
        this.debugMode = usePlugin(DebugModePlugin);
        this.state = proxy({
            home: null,
            course: null,
            step: null,
            file: 0,
            results: null,
            compare: null,
            showPasses: false,
            welcome: null,
            needName: false,
            seen: {},
            flashTabs: false,
            introPage: 1,
            treeFile: null,
            certificateDownloaded: {},
            treeWidth: Number(localStorage.getItem("om_academy_tree_width")) || null,
            hood: null,
            hoodOpen: false,
            sqlTyped: 0,
            note: null,
            warmup: null,
            askReset: false,
            busy: false,
        });
        // Under the hood, live: the tables refreshed while the panel is open
        this.hoodTimer = setInterval(() => this.refreshHood(), 3000);
        onWillUnmount(() => {
            clearInterval(this.hoodTimer);
            delete window.academy;
        });
        onWillStart(async () => {
            this.state.home = await this.orm.call(MODEL, "academy_home", []);
            if (this.state.home.welcome) {
                this.state.welcome = 0;  // the welcome guide, the first time
            }
        });
    }

    get modes() {
        return [
            ["live", _t("Build it live"), _t("No editor needed: see each step appear in Odoo.")],
            ["code", _t("Code it"), _t("Write the files in your editor; the Academy checks them.")],
        ];
    }

    html(value) {
        return value ? markup(value) : "";
    }

    /**
     * The explanation of a step, laid out to be read before the code: the first
     * paragraph as the idea, each list as numbered key points.
     */
    lesson(value) {
        if (!value) {
            return "";
        }
        const doc = new DOMParser().parseFromString(`<div>${value}</div>`, "text/html");
        const root = doc.body.firstElementChild;
        root.querySelector(":scope > p")?.classList.add("o_academy_lead");
        for (const list of root.querySelectorAll(":scope > ul, :scope > ol")) {
            const points = doc.createElement("div");
            points.className = "o_academy_points";
            [...list.children].forEach((item, index) => {
                const point = doc.createElement("div");
                point.className = "o_academy_point";
                const number = doc.createElement("span");
                number.className = "o_academy_point_num";
                number.textContent = index + 1;
                const body = doc.createElement("div");
                body.append(...item.childNodes);
                point.append(number, body);
                points.append(point);
            });
            list.replaceWith(points);
            // after the new words: what the code of the step does with them
            if (points.previousElementSibling?.tagName === "DL") {
                const title = doc.createElement("div");
                title.className = "o_academy_points_title";
                title.textContent = _t("What our code does");
                points.before(title);
            }
        }
        // the new words of the step, each explained in plain words
        for (const list of root.querySelectorAll(":scope > dl")) {
            const box = doc.createElement("div");
            box.className = "o_academy_words";
            const title = doc.createElement("div");
            title.className = "o_academy_words_title";
            title.textContent = _t("New words");
            box.append(title);
            for (const term of list.querySelectorAll(":scope > dt")) {
                const row = doc.createElement("div");
                row.className = "o_academy_word";
                const name = doc.createElement("span");
                name.className = "o_academy_word_term";
                name.append(...term.childNodes);
                const meaning = doc.createElement("span");
                meaning.className = "o_academy_word_meaning";
                if (term.nextElementSibling?.tagName === "DD") {
                    meaning.append(...term.nextElementSibling.childNodes);
                }
                row.append(name, meaning);
                box.append(row);
            }
            list.replaceWith(box);
        }
        return markup(root.innerHTML);
    }

    readMinutes(value) {
        const words = (value || "").replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
        return Math.max(1, Math.round(words / 180));
    }

    /** The module as folders and files, with what the step adds or changes. */
    get treeRows() {
        const rows = [];
        const folders = new Set();
        const module = this.state.course.module;
        for (const file of this.state.step.tree || []) {
            const parts = file.path.split("/");
            parts.slice(0, -1).forEach((part, depth) => {
                const folder = parts.slice(0, depth + 1).join("/");
                if (!folders.has(folder)) {
                    folders.add(folder);
                    rows.push({ key: folder, name: part + "/", depth: depth + 1, folder: true });
                }
            });
            rows.push({ key: file.path, name: parts.at(-1), depth: parts.length, status: file.status });
        }
        return module ? [{ key: "", name: module + "/", depth: 0, folder: true }, ...rows] : rows;
    }

    async run(callback) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            return await callback();
        } finally {
            this.state.busy = false;
        }
    }

    // navigation

    async showHome() {
        this.state.course = null;
        this.state.step = null;
        this.state.home = await this.orm.call(MODEL, "academy_home", []);
    }

    async openCourse(key, resume = false) {
        this.state.course = await this.orm.call(MODEL, "academy_open", [key]);
        if (this.state.course.notice) {
            this.notification.add(this.state.course.notice, { type: "warning", sticky: true });
            await this.refreshOdoo();
        }
        await this.openStep(resume ? this.state.course.current : 0);
    }

    async openStep(index, file = 0) {
        // the same step again (a mode or a level picked): stay on the page of the intro shown
        const page = this.state.step?.index === index ? this.state.introPage : null;
        this.state.results = null;
        this.state.compare = null;
        this.state.file = file;
        this.state.step = await this.orm.call(MODEL, "academy_step", [this.state.course.key, index]);
        this.state.introPage = page ?? this.introFirstPage;
        if (page === null || !this.codeTreeFile) {
            // the code tree opens on what the step adds, else on the manifest
            const tree = this.state.step.tree || [];
            const file = tree.find((item) => item.status !== "same") || tree.find((item) => item.path === "__manifest__.py");
            this.state.treeFile = file ? file.path : null;
        }
        if (page === null) {
            // another step: Under the hood closed, opened when the learner wants it
            this.state.hoodOpen = false;
            // another step: start reading it from the top
            document.querySelector(".o_academy_main")?.scrollTo({ top: 0 });
        }
        this.markSeen(file);
        this.state.hood = null;
        await this.loadHood(true);
    }

    // Under the hood: the database, live

    get hoodSql() {
        return (this.state.hood?.tables || []).map((table) => table.sql).filter(Boolean).join("\n\n");
    }

    async loadHood(typing = false) {
        const step = this.state.step;
        if (!step || step.intro || step.finish || !this.state.course) {
            return;
        }
        const previous = this.state.hood;
        const hood = await this.orm.call(MODEL, "academy_hood", [this.state.course.key, step.index]);
        // the rows added since the last look
        for (const table of hood.tables) {
            const before = previous?.tables.find((other) => other.table === table.table);
            table.grew = Boolean(before && table.count > before.count);
        }
        this.state.hood = hood;
        if (typing) {
            this.typeSql();
        }
    }

    typeSql() {
        clearInterval(this.sqlTimer);
        this.state.sqlTyped = 0;
        this.sqlTimer = setInterval(() => {
            this.state.sqlTyped += 4;
            if (this.state.sqlTyped >= this.hoodSql.length) {
                clearInterval(this.sqlTimer);
            }
        }, 30);
    }

    /** Under the hood opened: the SQL types itself again, for the learner to watch. */
    toggleHood(open) {
        if (open && !this.state.hoodOpen) {
            this.typeSql();
        }
        this.state.hoodOpen = open;
    }

    async refreshHood() {
        if (this.state.hoodOpen && this.state.hood && document.visibilityState === "visible" && !this.state.busy) {
            await this.loadHood();
        }
    }

    // the files of a step: the learner opens each one before going on

    get seenKey() {
        return `${this.state.course.key}:${this.state.step.index}`;
    }

    markSeen(file) {
        const seen = this.state.seen[this.seenKey] || [];
        if (!seen.includes(file)) {
            this.state.seen[this.seenKey] = [...seen, file];
        }
    }

    selectFile(file) {
        this.state.file = file;
        this.state.note = null;
        this.markSeen(file);
        // the code tree follows the tab opened
        const path = this.state.step.files[file]?.path.slice(this.state.course.module.length + 1);
        if (path && (this.state.step.tree || []).some((item) => item.path === path)) {
            this.state.treeFile = path;
        }
    }

    /** The file shown in the code tree, as it is after the step. */
    get codeTreeFile() {
        return (this.state.step.tree || []).find((file) => file.path === this.state.treeFile) || null;
    }

    /** The code tree is resized from its left edge: dragged left, it grows. */
    resizeTree(ev) {
        ev.preventDefault();
        const panel = ev.currentTarget.parentElement;
        const startX = ev.clientX;
        const startWidth = panel.getBoundingClientRect().width;
        const max = window.innerWidth - 280 - 480;  // the steps, and room for the lesson
        const move = (moveEv) => {
            this.state.treeWidth = Math.round(Math.min(max, Math.max(320, startWidth + startX - moveEv.clientX)));
        };
        const stop = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", stop);
            document.body.classList.remove("o_academy_resizing");
            if (this.state.treeWidth) {
                localStorage.setItem("om_academy_tree_width", this.state.treeWidth);
            }
        };
        document.body.classList.add("o_academy_resizing");
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop);
    }

    resetTreeWidth() {
        this.state.treeWidth = null;
        localStorage.removeItem("om_academy_tree_width");
    }

    /** The code tree: a file clicked shows its code, and opens its tab when the step has it. */
    showTreeFile(row) {
        if (row.folder) {
            return;
        }
        this.state.treeFile = row.key;
        const path = `${this.state.course.module}/${row.key}`;
        const index = this.state.step.files.findIndex((file) => file.path === path);
        if (index >= 0) {
            this.selectFile(index);
        }
    }

    openTreeFile(row) {
        // a file of the step, from "Where it goes": open its tab in the code below
        const path = `${this.state.course.module}/${row.key}`;
        const index = this.state.step.files.findIndex((file) => file.path === path);
        if (index < 0) {
            return;
        }
        this.selectFile(index);
        document.querySelector(".o_academy_code")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    isSeen(file) {
        return (this.state.seen[this.seenKey] || []).includes(file);
    }

    /** The files not opened yet; none once the step is built or checked. */
    get unseen() {
        const step = this.state.step;
        if (step.built || step.done) {
            return [];
        }
        return step.files.map((file, index) => index).filter((index) => !this.isSeen(index));
    }

    /** Asks the learner to open the files not opened yet, if any: true when it did. */
    showUnseen() {
        const unseen = this.unseen;
        if (!unseen.length) {
            return false;
        }
        this.notification.add(
            _t("Check each file of this step first: click the tabs marked with a dot (%(count)s to go).", {
                count: unseen.length,
            }),
            { type: "warning" }
        );
        this.state.flashTabs = true;
        setTimeout(() => (this.state.flashTabs = false), 1600);
        document.querySelector(".o_academy_code")?.scrollIntoView({ behavior: "smooth", block: "center" });
        return true;
    }

    // explain this line

    toggleNote(line) {
        if (!line.note) {
            return;
        }
        const key = `${this.state.file}:${line.number}`;
        this.state.note = this.state.note === key ? null : key;
    }

    isNoteOpen(line) {
        return this.state.note === `${this.state.file}:${line.number}`;
    }

    // celebrate

    get cheers() {
        return [
            _t("Built! Nice work."),
            _t("Look at you go!"),
            _t("One more step: you are getting good at this."),
            _t("That is how Odoo developers do it."),
            _t("Smooth! On to the next one."),
            _t("Your app grows, step by step."),
        ];
    }

    /** A cheer for a step done; the rainbow man of Odoo for a whole app. */
    celebrate(appDone) {
        if (appDone) {
            this.effect.add({
                type: "rainbow_man",
                message: _t("You built %(app)s! Nothing is too big: what is your next app?", {
                    app: this.state.course.app_name,
                }),
                fadeout: "slow",
            });
            return;
        }
        const cheer = this.cheers[Math.floor(Math.random() * this.cheers.length)];
        const refresh = this.state.step.mode === "live" ? " " + _t("Refresh your other tab to see it.") : "";
        this.notification.add(cheer + refresh, { type: "success" });
    }

    get appDone() {
        return this.state.course.steps.every((step) => step.intro || step.done);
    }

    /** The intro has up to three pages: the app to build (its preview), what we will build, make it yours. */
    get introFirstPage() {
        return this.state.step.intro && this.state.step.preview ? 0 : 1;
    }

    get introPreview() {
        return this.state.step.intro && this.state.introPage === 0;
    }

    get introYours() {
        return this.state.step.intro && this.state.introPage === 2;
    }

    async next() {
        if (this.introYours) {
            // typed, then Next at once: wait for the name to be saved, once
            const typed = document.querySelector(".o_academy_author_name")?.value.trim();
            if (typed && typed !== this.state.course.author_name) {
                await this.saveName(typed);
            }
            if (!this.state.course.author_name) {
                this.focusName();
                return;
            }
        }
        if (this.state.step.intro && this.state.introPage < 2) {
            this.state.introPage += 1;
            document.querySelector(".o_academy_main")?.scrollTo({ top: 0 });
            return;
        }
        if (!this.canNext || this.showUnseen()) {
            return;
        }
        await this.openStep(this.state.step.index + 1);
    }

    async previous() {
        if (this.state.step.intro && this.state.introPage > this.introFirstPage) {
            this.state.introPage -= 1;
            document.querySelector(".o_academy_main")?.scrollTo({ top: 0 });
            return;
        }
        await this.openStep(this.state.step.index - 1);
    }

    get firstApps() {
        return this.state.home.courses.filter((course) => course.family === "first_app");
    }

    get otherCourses() {
        return this.state.home.courses.filter((course) => course.family !== "first_app");
    }

    get nextCourse() {
        // the one to open now: the last one opened, another one started, then the first not done
        const courses = [...this.firstApps, ...this.otherCourses];
        const open = (course) => course.done < course.steps;
        return (
            courses.find((course) => course.key === this.state.home.last && open(course)) ||
            courses.find((course) => course.started && open(course)) ||
            courses.find(open) ||
            null
        );
    }

    get homeStats() {
        const courses = this.state.home.courses;
        const steps = courses.reduce((total, course) => total + course.steps, 0);
        const stepsDone = courses.reduce((total, course) => total + course.done, 0);
        return {
            courses: courses.length,
            coursesDone: courses.filter((course) => course.done === course.steps).length,
            steps,
            stepsDone,
            percent: steps ? Math.round((100 * stepsDone) / steps) : 0,
        };
    }

    get failures() {
        return this.state.results.results.filter((result) => !result.ok);
    }

    get successes() {
        return this.state.results.results.filter((result) => result.ok);
    }

    get hasNext() {
        return this.state.step.index < this.state.course.steps.length - 1;
    }

    /** Step by step: Next once the step is built (or checked, in code). */
    get canNext() {
        const step = this.state.step;
        return !step.buildable || (step.mode === "live" ? step.built : step.done);
    }

    /** The last step the learner may open: the first one not built yet. */
    get lastOpenStep() {
        const step = this.state.course.steps.find((item) => !item.intro && !item.done);
        return step ? step.index : this.state.course.steps.length - 1;
    }

    isLocked(item) {
        return item.index > this.lastOpenStep;
    }

    openStepItem(item) {
        if (this.isLocked(item)) {
            this.notification.add(_t("One step at a time: build this step first, then Next."), { type: "info" });
            return;
        }
        return this.openStep(item.index);
    }

    // modes

    async setMode(mode) {
        this.state.course = await this.orm.call(MODEL, "academy_set_mode", [this.state.course.key, mode]);
        await this.openStep(this.state.step.index);
    }

    async setLevel(level) {
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_set_level", [this.state.course.key, level]);
            if (result.type) {
                // Discuss was installed: the web client reloads, back to the Academy
                await this.action.doAction(result);
                return;
            }
            this.state.course = result;
            await this.refreshOdoo();
            await this.openStep(0);
        });
    }

    async setIdentity(values) {
        this.state.course = await this.orm.call(MODEL, "academy_set_identity", [this.state.course.key, values]);
        this.state.needName = !this.state.course.author_name && this.state.needName;
        const page = this.state.introPage;
        await this.openStep(this.state.step.index, this.state.file);
        this.state.introPage = page;
        if ("icon" in values || "icon_data" in values) {
            await this.refreshOdoo();
        }
    }

    async uploadIcon(ev) {
        const file = ev.target.files[0];
        if (!file) {
            return;
        }
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        await this.run(() => this.setIdentity({ icon_data: data }));
        ev.target.value = "";
    }

    get welcomeScreens() {
        return ["welcome", "ways", "path", "us"];
    }

    async closeWelcome() {
        this.state.welcome = null;
        if (this.state.home.welcome) {
            this.state.home.welcome = false;
            await this.orm.call(MODEL, "academy_welcomed", []);
        }
    }

    // the warm-up: how well do you know Odoo?

    async openWarmup() {
        this.state.welcome = null;
        const data = await this.orm.call("academy.warmup", "academy_warmup", []);
        this.state.warmup = {
            data, tab: "quiz", view: "pick", current: 0, result: null, app: "", technical: "", results: {}, found: {}, findResults: {},
        };
        // Find it: the console has a word for the learner
        window.academy = {
            secret() {
                console.log("%c🎓 Odoo Mates Academy: your secret word is " + data.secret, "color: #715782; font-size: 16px; font-weight: bold;");
                return data.secret;
            },
        };
        // back to a round left half done: on its first question not answered
        const round = data.round;
        if (round && !round.finished) {
            this.state.warmup.view = "round";
            this.state.warmup.current = Math.max(0, round.questions.findIndex((question) => !question.answer));
        }
    }

    /** A new round of the topic: other questions, in another order. */
    async startRound(topic) {
        const warmup = this.state.warmup;
        warmup.data = await this.orm.call("academy.warmup", "academy_warmup_start", [topic]);
        Object.assign(warmup, { view: "round", current: 0, result: null });
    }

    get warmupQuestion() {
        const warmup = this.state.warmup;
        return warmup.data.round?.questions[warmup.current];
    }

    get warmupTopic() {
        const warmup = this.state.warmup;
        return warmup.data.topics.find((topic) => topic.key === warmup.data.round?.topic);
    }

    get warmupCheer() {
        const { score, total } = this.state.warmup.result;
        if (score === total) {
            return { emoji: "🏆", title: _t("Perfect!"), text: _t("Every answer right. You know your Odoo.") };
        }
        if (score >= total * 0.6) {
            return { emoji: "🎉", title: _t("Well done!"), text: _t("A fine round. Another one, to make it perfect?") };
        }
        return { emoji: "💪", title: _t("You did it!"), text: _t("Every round teaches something: read the answers, and try another one.") };
    }

    async answer(question, choice) {
        if (question.answer) {
            return;
        }
        const answer = await this.orm.call("academy.warmup", "academy_warmup_answer", [question.key, choice]);
        question.answer = answer;
        this.state.warmup.data.round.score += answer.correct ? 1 : 0;
        this.state.warmup.result = answer.result || null;
    }

    async nextQuestion() {
        const warmup = this.state.warmup;
        if (warmup.result) {
            // the round is done: the scores of the topics, up to date
            const result = warmup.result;
            warmup.data = await this.orm.call("academy.warmup", "academy_warmup", []);
            Object.assign(warmup, { view: "done", result });
            return;
        }
        warmup.current += 1;
    }

    /** Find it: what the learner found, checked against the database. */
    async checkFind(find) {
        const warmup = this.state.warmup;
        const value = find.key === "debug" ? this.debugMode.isActive() : warmup.found[find.key] || "";
        const result = await this.orm.call("academy.warmup", "academy_warmup_find", [find.key, value]);
        warmup.findResults[find.key] = result;
        if (result.ok) {
            find.done = result.message;
        }
    }

    async checkTask(task) {
        const value = task.key === "app" ? this.state.warmup.app : task.key === "technical" ? this.state.warmup.technical : null;
        const result = await this.orm.call("academy.warmup", "academy_warmup_check", [task.key, value]);
        this.state.warmup.results[task.key] = result;
        if (result.ok) {
            task.done = result.message;
        }
    }

    // Your turn

    async checkChallenge(challenge) {
        const result = await this.orm.call(MODEL, "academy_challenge_check", [this.state.course.key, challenge.key]);
        challenge.result = result;
        if (!result.ok) {
            return;
        }
        challenge.done = true;
        if (result.all_done) {
            this.effect.add({
                type: "rainbow_man",
                message: _t("All the challenges done, on your own! You are an Odoo developer now."),
                fadeout: "slow",
            });
        } else {
            this.notification.add(_t("Challenge done!"), { type: "success" });
        }
    }

    async certificateAll() {
        await this.action.doAction(await this.orm.call(MODEL, "academy_certificate_all", []));
    }

    async certificate(courseKey) {
        const key = courseKey || this.state.course.key;
        const action = await this.orm.call(MODEL, "academy_certificate", [key]);
        await this.action.doAction(action);
        // downloaded: now show how Odoo made it
        localStorage.setItem(`om_academy_certificate_${key}`, "1");
        this.state.certificateDownloaded = { ...this.state.certificateDownloaded, [key]: true };
    }

    get certificateDownloaded() {
        const key = this.state.course.key;
        return Boolean(this.state.certificateDownloaded?.[key] || localStorage.getItem(`om_academy_certificate_${key}`));
    }

    async certificateBehind(what) {
        await this.action.doAction(await this.orm.call(MODEL, "academy_certificate_behind", [what]));
    }

    get links() {
        return [
            ["GitHub: odoomates", "https://github.com/odoomates"],
            ["GitHub: niyasraphy", "https://github.com/niyasraphy"],
            ["LinkedIn: Niyas Raphy", "https://www.linkedin.com/in/niyasraphy/"],
        ];
    }

    async setPath(ev) {
        this.state.course = await this.orm.call(MODEL, "academy_set_path", [this.state.course.key, ev.target.value]);
    }

    /**
     * After the database changed: the views the browser keeps are stale (a field
     * of a cached form may be gone), and the menus too.
     */
    async refreshOdoo() {
        rpcBus.trigger("CLEAR-CACHES", "get_views");
        await this.menu.reload();
    }

    // Build it live

    /**
     * The learner is the author of their app: no build, no file written, before
     * they write their name. Takes them to it.
     */
    async askName() {
        if (this.state.course.author_name) {
            return false;
        }
        // Make it yours, the last page of the intro: the name goes there
        await this.openStep(0);
        this.state.introPage = 2;
        this.focusName();
        return true;
    }

    /** Saves the name of the learner: one save per name, whoever asks (the field, Next). */
    saveName(name) {
        if (!this.nameSaving || this.nameSaving.name !== name) {
            const promise = this.setIdentity({ author_name: name });
            this.nameSaving = { name, promise };
            promise.finally(() => {
                if (this.nameSaving?.promise === promise) {
                    this.nameSaving = null;
                }
            });
        }
        return this.nameSaving.promise;
    }

    focusName() {
        this.state.needName = true;
        this.notification.add(_t("Write your name first: you are the author of this app."), { type: "warning" });
        setTimeout(() => document.querySelector(".o_academy_author_name")?.focus(), 150);
    }

    get shareText() {
        return _t(
            "I just built %(app)s, my first Odoo app, with the Odoo Mates Academy. Odoo development is so cool to start! 🚀",
            { app: this.state.course.app_name }
        );
    }

    get shareLinks() {
        const url = encodeURIComponent(this.state.course.share_url);
        const text = encodeURIComponent(this.shareText);
        return [
            ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${url}`],
            ["X", `https://twitter.com/intent/tweet?text=${text}&url=${url}`],
            ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${url}`],
            ["WhatsApp", `https://wa.me/?text=${text}%20${url}`],
        ];
    }

    async copyShare() {
        await navigator.clipboard.writeText(`${this.shareText} ${this.state.course.share_url}`);
        this.notification.add(_t("Copied: paste it anywhere you like."), { type: "info" });
    }

    async build() {
        if ((await this.askName()) || this.showUnseen()) {
            return;
        }
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_build", [this.state.course.key, this.state.step.index]);
            const wasDone = this.appDone;
            this.state.course = result.course;
            this.state.step = result;
            await this.refreshOdoo();
            await this.loadHood(true);
            this.celebrate(!wasDone && this.appDone);
        });
    }

    async undo() {
        await this.run(async () => {
            this.state.course = await this.orm.call(MODEL, "academy_undo", [this.state.course.key]);
            await this.refreshOdoo();
            await this.openStep(this.state.step.index);
        });
    }

    async reset(keep) {
        this.state.askReset = false;
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_reset", [this.state.course.key], { keep });
            if (result.type) {
                // the module was uninstalled: the web client reloads, back to the Academy
                await this.action.doAction(result);
                return;
            }
            this.state.course = result;
            await this.refreshOdoo();
            if (keep && this.state.step.mode === "live") {
                this.notification.add(
                    _t("Your app stays in Apps: uninstall it there when you like. Pick your next one!"),
                    { type: "success" }
                );
                await this.showHome();
                return;
            }
            await this.openStep(0);
        });
    }

    // Code it

    async writeFiles() {
        if ((await this.askName()) || this.showUnseen()) {
            return;
        }
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_write", [this.state.course.key, this.state.step.index]);
            this.notification.add(
                _t("%(count)s files written in %(path)s", { count: result.files.length, path: result.path }),
                { type: "success" }
            );
        });
    }

    /** Restart Odoo for the Python of the step, wait for it, then upgrade the module. */
    async restartAndUpgrade() {
        await this.run(async () => {
            this.notification.add(_t("Odoo restarts: a few seconds..."), { type: "info" });
            await this.orm.call(MODEL, "academy_restart", []);
            await this.waitForOdoo();
            const action = await this.orm.call(MODEL, "academy_install", [this.state.course.key]);
            await this.action.doAction(action);
        });
    }

    async waitForOdoo() {
        const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const up = async () => {
            try {
                return (await fetch("/web/health", { cache: "no-store" })).ok;
            } catch {
                return false;
            }
        };
        // down first (it may be quick), then up again
        for (let tries = 0; tries < 16 && (await up()); tries++) {
            await wait(500);
        }
        for (let tries = 0; tries < 240 && !(await up()); tries++) {
            await wait(500);
        }
    }

    async install() {
        await this.run(async () => {
            const action = await this.orm.call(MODEL, "academy_install", [this.state.course.key]);
            await this.action.doAction(action);
        });
    }

    async check() {
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_check", [this.state.course.key, this.state.step.index]);
            this.state.results = result;
            this.state.course = result.course;
            this.state.step.done = result.passed;
            this.state.step.can_see = this.state.step.can_see_after_check && result.passed;
            if (result.passed) {
                this.celebrate(this.appDone);
            }
        });
    }

    // the finish

    async exportApp() {
        const action = await this.orm.call(MODEL, "academy_export", [this.state.course.key]);
        await this.action.doAction(action);
    }

    continueInCode() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Continue in code"),
            body: _t(
                "Your module is written in your addons folder, and the app built live makes room for it: it is uninstalled, with the records you typed in it. Then click Install."
            ),
            confirmLabel: _t("Continue in code"),
            confirm: () => this.doContinueInCode(),
            cancel: () => {},
        });
    }

    async doContinueInCode() {
        await this.run(async () => {
            const result = await this.orm.call(MODEL, "academy_continue", [this.state.course.key]);
            this.state.course = result.course;
            this.notification.add(
                _t(
                    "Your module is in %(path)s: open it in your editor. The app built live made room for it: click Install. You are now in Code it.",
                    { path: result.path }
                ),
                { type: "success", sticky: true }
            );
            await this.openStep(this.state.step.index);
        });
    }

    async compare() {
        await this.run(async () => {
            this.state.compare = await this.orm.call(MODEL, "academy_compare", [this.state.course.key, this.state.step.index]);
        });
    }

    // both

    /** See it in Odoo, in a new tab: the course stays where it is. */
    async see() {
        const url = await this.orm.call(MODEL, "academy_see_url", [this.state.course.key, this.state.step.index]);
        if (url) {
            window.open(url, "_blank");
            return;
        }
        const action = await this.orm.call(MODEL, "academy_see", [this.state.course.key, this.state.step.index]);
        await this.action.doAction(action);
    }

    async copy(file) {
        await navigator.clipboard.writeText(file.content);
        this.notification.add(_t("Copied: %s", file.path), { type: "info" });
    }
}

registry.category("actions").add("om_academy.academy", Academy);
