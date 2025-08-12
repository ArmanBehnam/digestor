import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import networkx as nx
import numpy as np


def create_super_fancy_architecture():

    G = nx.DiGraph()

    nodes = {
        'PDF': {
            'pos': (0, 6), 'category': 'input', 'size': 60,
            'label': '<br><b>Input PDF</b><br>',
            'description': 'Complex engineering drawings and specifications'
        },

        'Orchestrator': {
            'pos': (0, 4), 'category': 'orchestrator', 'size': 70,
            'label': '<br><b>Orchestrator Agent</b><br><i>(LangChain Coordinator)</i>',
            'description': 'Manages workflow, state, and error recovery'
        },

        # Processing Agents Layer
        'OCR_Agent': {
            'pos': (-3, 2), 'category': 'agent', 'size': 50,
            'label': '<br><b>OCR Agent</b><br><i>Multi-Engine Processing</i>',
            'description': 'Hierarchical OCR with intelligent fallback'
        },
        'QA_Agent': {
            'pos': (3, 2), 'category': 'agent', 'size': 50,
            'label': '<br><b>Engineering QA Agent</b><br><i>Hierarchical LLM</i>',
            'description': '26 engineering questions with domain expertise'
        },

        # OCR Engines - Left side
        'AWS_Textract': {
            'pos': (-5, 0), 'category': 'ocr_engine', 'size': 50,
            'label': '<br><b>AWS Textract</b><br><i>Priority 1</i>',
            'description': 'Primary OCR engine'
        },
        'Claude_OCR': {
            'pos': (-4, 0), 'category': 'ocr_engine', 'size': 50,
            'label': '<br><b>Claude OCR</b><br><i>Priority 2</i>',
            'description': 'Fallback OCR engine'
        },
        'Tessseract_OCR': {
            'pos': (-3, 0), 'category': 'ocr_engine', 'size': 50,
            'label': '<br><b>Tessseract OCR</b><br><i>Priority 3</i>',
            'description': 'AI-powered OCR'
        },
        'Arman_OCR': {
            'pos': (-2, 0), 'category': 'ocr_engine', 'size': 50,
            'label': '<br><b>Arman OCR</b><br><i>Fallback</i>',
            'description': 'Local OCR fallback'
        },

        'GPT4o': {
            'pos': (2, 0), 'category': 'llm_engine', 'size': 50,
            'label': '<br><b>GPT-4o</b><br>',
            'description': 'Primary LLM with highest rate limits'
        },
        'Claude_Sonnet': {
            'pos': (3, 0), 'category': 'llm_engine', 'size': 50,
            'label': '<br><b>Claude Sonnet 4</b><br>',
            'description': 'Fallback 1 - Superior reasoning'
        },
        'DeepSeek': {
            'pos': (4, 0), 'category': 'llm_engine', 'size': 50,
            'label': '<br><b>DeepSeek R1</b><br>',
            'description': 'Fallback 2 - Cost optimization'
        },

        'Pattern_Extract': {
            'pos': (-3, -2), 'category': 'processing', 'size': 50,
            'label': '<br><b>Pattern Recognition</b><br><i>80+ Engineering Patterns</i>',
            'description': 'Building codes, deflection, loads extraction'
        },
        'Question_Process': {
            'pos': (3, -2), 'category': 'processing', 'size': 50,
            'label': '<br><b>Question Processing</b><br><i>26 Domain Questions</i>',
            'description': 'Engineering domain expertise with prompt engineering'
        },

        # Integration Layer
        'Legacy_System': {
            'pos': (-6, 2), 'category': 'integration', 'size': 60,
            'label': '<br><b>Legacy Integration</b><br><i>Existing Codebase</i>',
            'description': 'OCR Tools & LLM Tools integration'
        },
        'LangChain': {
            'pos': (6, 2), 'category': 'integration', 'size': 60,
            'label': '<br><b>LangChain</b><br><i>Agent Framework</i>',
            'description': 'Multi-agent orchestration framework'
        },

        # Output Layer
        'Results_CSV': {
            'pos': (-1.5, -4), 'category': 'output', 'size': 60,
            'label': '<br><b>Engineering CSV</b><br><i>26 Answers + Defaults</i>',
            'description': 'Structured engineering data with confidence scores'
        },
        'Results_JSON': {
            'pos': (1.5, -4), 'category': 'output', 'size': 60,
            'label': '<br><b>Metadata JSON</b><br><i>Processing Metrics</i>',
            'description': 'Performance metrics and agent statistics'
        },

        # Performance Metrics
        'Metrics': {
            'pos': (0, -6), 'category': 'metrics', 'size': 30,
            'label': '<br><b>Production Ready</b><br>',
            'description': 'Real-world performance metrics'
        }
    }

    # Add nodes to graph
    for node_id, data in nodes.items():
        G.add_node(node_id, **data)

    # Enhanced connections with better flow
    edges = [
        # Main flow
        ('PDF', 'Orchestrator'),
        ('Orchestrator', 'OCR_Agent'),
        ('Orchestrator', 'QA_Agent'),

        # OCR connections
        ('OCR_Agent', 'AWS_Textract'),
        ('OCR_Agent', 'Claude_OCR'),
        ('OCR_Agent', 'Tessseract_OCR'),
        ('OCR_Agent', 'Arman_OCR'),
        ('OCR_Agent', 'Pattern_Extract'),

        # LLM connections
        ('QA_Agent', 'GPT4o'),
        ('QA_Agent', 'Claude_Sonnet'),
        ('QA_Agent', 'DeepSeek'),
        ('QA_Agent', 'Question_Process'),

        # Integration
        ('Legacy_System', 'OCR_Agent'),
        ('LangChain', 'Orchestrator'),

        # Results flow
        ('Pattern_Extract', 'Results_CSV'),
        ('Question_Process', 'Results_JSON'),
        ('Results_CSV', 'Metrics'),
        ('Results_JSON', 'Metrics'),
    ]

    G.add_edges_from(edges)

    # Premium color scheme
    colors = {
        'input': '#FF6B6B',  # Vibrant red
        'orchestrator': '#4ECDC4',  # Teal
        'agent': '#45B7D1',  # Blue
        'ocr_engine': '#96CEB4',  # Mint green
        'llm_engine': '#FFEAA7',  # Gold
        'processing': '#DDA0DD',  # Plum
        'integration': '#FFB347',  # Orange
        'output': '#98D8C8',  # Light teal
        'metrics': '#F7DC6F'  # Light gold
    }

    # Create enhanced figure
    fig = go.Figure()

    # Add gradient background
    fig.add_shape(
        type="rect",
        x0=-7, y0=-7, x1=7, y1=7,
        fillcolor="rgba(248,249,250,0.3)",
        line=dict(width=0),
        layer="below"
    )

    # Add enhanced edges with varying thickness
    for edge in G.edges():
        x0, y0 = nodes[edge[0]]['pos']
        x1, y1 = nodes[edge[1]]['pos']

        # Determine edge style based on connection type
        if edge[0] == 'Orchestrator' or edge[1] == 'Orchestrator':
            line_width = 4
            line_color = 'rgba(78,205,196,0.8)'
        elif 'Agent' in edge[0] or 'Agent' in edge[1]:
            line_width = 3
            line_color = 'rgba(69,183,209,0.6)'
        else:
            line_width = 2
            line_color = 'rgba(125,125,125,0.4)'

        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            line=dict(width=line_width, color=line_color),
            hoverinfo='none',
            mode='lines',
            showlegend=False
        ))

    # Add nodes with enhanced styling
    for category, color in colors.items():
        category_nodes = [n for n, d in nodes.items() if d['category'] == category]

        if not category_nodes:
            continue

        node_x = [nodes[n]['pos'][0] for n in category_nodes]
        node_y = [nodes[n]['pos'][1] for n in category_nodes]
        node_sizes = [nodes[n]['size'] for n in category_nodes]
        node_labels = [nodes[n]['label'] for n in category_nodes]
        node_descriptions = [nodes[n]['description'] for n in category_nodes]

        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            marker=dict(
                size=node_sizes,
                color=color,
                line=dict(width=3, color='rgba(50,50,50,0.7)'),
                opacity=0.9,
                symbol='circle'
            ),
            text=node_labels,
            textposition="middle center",
            textfont=dict(
                size=11,
                color='black',
                family="Arial Black, sans-serif"
            ),
            name=category.replace('_', ' ').title(),
            hovertemplate='<b>%{text}</b><br>%{customdata}<extra></extra>',
            customdata=node_descriptions
        ))

    fig.update_layout(
        title={
            'text': '<b style="font-size:28px; color:#2C3E50;">Multi-Agent Digestor Architecture</b><br><span style="font-size:18px; color:#34495E;"><i>LangChain-Orchestrated Engineering Document Processing Pipeline</i></span><br><span style="font-size:14px; color:#7F8C8D;"></span>',
            'x': 0.5,
            'font': {'family': 'Arial Black, sans-serif'}
        },
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(size=12, family="Arial, sans-serif")
        ),
        hovermode='closest',
        margin=dict(b=100, l=50, r=50, t=120),
        annotations=[
            dict(
                text="<b>Hierarchical LLM Engines</b> with Automatic Fallback | <b>6 OCR Engines</b> with Priority-Based Selection | <b>80+ Engineering Patterns</b> | <b>26 Domain Questions</b>",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.5, y=-0.08,
                xanchor='center', yanchor='bottom',
                font=dict(color='#34495E', size=13, family="Arial, sans-serif")
            ),
        ],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7.5, 7.5]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-7, 7.5]),
        plot_bgcolor='rgba(255,255,255,0.95)',
        paper_bgcolor='white',
        font=dict(family="Arial, sans-serif"),
        width=1400,
        height=1000
    )

    return fig


if __name__ == "__main__":
    fig = create_super_fancy_architecture()
    fig.write_html("multi_agent_digestor.html")
    fig.show()
    print("Multi-Agent-Digestor is ready")
