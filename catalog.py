from flask import Flask
from flask import render_template
from flask import url_for
from flask import request
from flask import redirect
from flask import flash
from flask import jsonify
from flask import make_response
from flask import session as login_session

import random
import string
import httplib2
import json
import requests

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database_setup import Base
from database_setup import User
from database_setup import Brewery
from database_setup import Beer

app = Flask(__name__)

CLIENT_ID = json.loads(
  open('client_secrets.json', 'r').read())['web']['client_id']


engine = create_engine('sqlite:///beercatalogwithusers.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
        # Obtain authorization connected

    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps(
                    'Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps(
                    "Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(json.dumps(
                    "Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps(
                    'Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])

    if not user_id:
        user_id = createUser(login_session)
        login_session['user_id'] = user_id

    output = ''
    output += '<h1 class="display-4">Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 150px; height: 150px;border-radius: 75px;" '
    output += ' -webkit-border-radius: 75px;-moz-border-radius: 75px;"> '
    flash("Welcome, %s!" % login_session['username'])
    print "done!"
    return output


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user not connected.'),
                                 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    flash("%s has been successfully logged out" % login_session['username'])
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return redirect('/')
    else:
        response = make_response(json.dumps(
                                'Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/catalog/JSON')
def breweriesJSON():
    breweries = session.query(Brewery).all()
    beers = session.query(Beer).all()
    return jsonify(Breweries=[i.serialize for i in breweries])


@app.route('/brewery/<int:brewery_id>/beers/JSON')
def beersJSON(brewery_id):
    brewery = session.query(Brewery).filter_by(id=brewery_id).one()
    beers = session.query(Beer).filter_by(brewery_id=brewery_id).all()
    return jsonify(Beers=[i.serialize for i in beers])


@app.route('/')
def showBreweries():
    breweries = session.query(Brewery).all()
    beers = session.query(Beer).all()
    if 'username' not in login_session:
        return render_template('publicbreweries.html', breweries=breweries,
                               beers=beers)
    else:
        return render_template('breweries.html', breweries=breweries,
                               beers=beers)


@app.route('/brewery/new', methods=['GET', 'POST'])
def newBrewery():
    if 'username' not in login_session:
        flash("You must log in to add a brewery.")
        return redirect('/')
    if request.method == 'POST':
        newBrewery = Brewery(name=request.form['name'],
                             location=request.form['location'],
                             user_id=login_session['user_id'])
        session.add(newBrewery)
        session.commit()
        flash("%s created successfully!" % newBrewery.name)
        return redirect(url_for('showBreweries',))
    else:
        return render_template('newbrewery.html', user_id=id)


@app.route('/brewery/<int:brewery_id>/edit', methods=['GET', 'POST'])
def editBrewery(brewery_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedBrewery = session.query(Brewery).filter_by(id=brewery_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedBrewery.name = request.form['name']
        if request.form['location']:
            editedBrewery.location = request.form['location']
        session.add(editedBrewery)
        session.commit()
        flash("%s edited successfully!" % editedBrewery.name)
        return redirect(url_for('showBeers', brewery_id=brewery_id))
    else:
        return render_template('editbrewery.html', brewery=editedBrewery)


@app.route('/brewery/<int:brewery_id>/delete', methods=['GET', 'POST'])
def deleteBrewery(brewery_id):
    if 'username' not in login_session:
        return redirect('/login')
    deletedBrewery = session.query(Brewery).filter_by(id=brewery_id).one()
    if request.method == 'POST':
        session.delete(deletedBrewery)
        session.commit()
        flash("%s deleted successfully!" % deletedbrewery.name)
        return redirect(url_for('showBreweries'))
    else:
        return render_template('deletebrewery.html', brewery=deletedBrewery)


@app.route('/brewery/<int:brewery_id>/beers')
def showBeers(brewery_id):
    brewery = session.query(Brewery).filter_by(id=brewery_id).one()
    creator = getUserInfo(brewery.user_id)
    beers = session.query(Beer).filter_by(brewery_id=brewery_id)
    if 'username' not in login_session \
            or creator.email != login_session['email']:
        return render_template('publicbeers.html', brewery=brewery,
                               beers=beers, creator=creator)
    else:
        return render_template('beers.html', brewery=brewery, beers=beers,
                               creator=creator)


@app.route('/brewery/<int:brewery_id>/new', methods=['GET', 'POST'])
def newBeer(brewery_id):
    if 'username' not in login_session:
        return redirect('/login')
    brewery = session.query(Brewery).filter_by(id=brewery_id).one()
    if request.method == 'POST':
        newBeer = Beer(name=request.form['name'],
                       description=request.form['description'],
                       style=request.form['style'],
                       abv=request.form['abv'],
                       ibu=request.form['ibu'],
                       brewery_id=brewery_id,
                       user_id=login_session['user_id'])
        session.add(newBeer)
        session.commit()
        flash("%s added successfully!" % newBeer.name)
        return redirect(url_for('showBeers', brewery_id=brewery_id))
    else:
        return render_template('newbeer.html', brewery=brewery)


@app.route('/brewery/<int:brewery_id>/beers/<int:beer_id>/edit',
           methods=['GET', 'POST'])
def editBeer(brewery_id, beer_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedBeer = session.query(Beer).filter_by(id=beer_id).one()
    if request.method == 'POST':
        if request.form['name']:
            editedBeer.name = request.form['name']
        if request.form['description']:
            editedBeer.description = request.form['description']
        if request.form['style']:
            editedBeer.style = request.form['style']
        if request.form['abv']:
            editedBeer.abv = request.form['abv']
        if request.form['ibu']:
            editedBeer.ibu = request.form['ibu']
        session.add(editedBeer)
        session.commit()
        flash("%s edited successfully!" % editedBeer.name)
        return redirect(url_for('showBeers', brewery_id=brewery_id))
    else:
        return render_template('editbeer.html', brewery_id=brewery_id,
                               beer=editedBeer)


@app.route('/brewery/<int:brewery_id>/beers/<int:beer_id>/delete',
           methods=['GET', 'POST'])
def deleteBeer(brewery_id, beer_id):
    if 'username' not in login_session:
        return redirect('/login')
    deletedBeer = session.query(Beer).filter_by(id=beer_id).one()
    if request.method == 'POST':
        session.delete(deletedBeer)
        session.commit()
        flash("%s deleted successfully!" % deletedBeer.name)
        return redirect(url_for('showBeers', brewery_id=brewery_id))
    else:
        return render_template('deletebeer.html', beer=deletedBeer,
                               brewery_id=brewery_id)


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


def getUserInfo(user_id):
    try:
        user = session.query(User).filter_by(id=user_id).one()
        return user
    except:
        return None


def createUser(login_session):
    newUser = User(name=login_session['username'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
